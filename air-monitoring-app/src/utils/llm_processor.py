"""
LLM-based structured data extraction for Air Monitoring V2.
Adapted from V1 llm_utils prompt — proven in production.
Reads OpenAI config from config.py (hardcoded same as V1).
"""
import json
import re
from datetime import datetime
from openai import AzureOpenAI
from utils.config import get_openai_config


def _get_openai_client() -> AzureOpenAI:
    """Get Azure OpenAI client — same credentials as V1."""
    return AzureOpenAI(
        azure_endpoint=get_openai_config()["endpoint"],
        api_key=get_openai_config()["api_key"],
        api_version=get_openai_config()["api_version"],
    )


# ============================================================
# V1-proven extraction prompt — adapted for JSON output
# ============================================================

# ============================================================
# Analysis Method Normalization
# GPT sometimes returns non-English or variant names.
# This mapping ensures consistent output.
# ============================================================

_ELECTRON_MICROSCOPY_VARIANTS = [
    "electron microscopy",
    "transmission electron microscopy",
    "scanning electron microscopy",
    "microscopie electronique",
    "microscopie électronique",
    "microscopie electronique a transmission",
    "microscopie électronique à transmission analytique",
    "meta",  # French abbreviation for Microscopie Electronique a Transmission Analytique
    "tem",
    "sem",
    "elektronenmikroskopie",
    "transmissionselektronenmikroskopie",
    "microscopia electrónica",
    "microscopia elettronica",
]

_OPTICAL_MICROSCOPY_VARIANTS = [
    "optical microscopy",
    "phase contrast microscopy",
    "pcm",
    "microscopie optique",
    "microscopie optique a contraste de phase",
    "microscopie optique à contraste de phase",
    "mocp",
    "lichtmikroskopie",
    "phasenkontrastmikroskopie",
    "microscopia óptica",
    "microscopia ottica",
    "optische microscopie",
    "fasecontrastmicroscopie",
]


def _normalize_analysis_method(raw_value) -> str:
    """Normalize Analysis_method to one of: 'Optical Microscopy', 'Electron Microscopy', or None."""
    if not raw_value or str(raw_value).lower().strip() in ("null", "none", "nan", "not specified", ""):
        return None
    
    val = str(raw_value).lower().strip()
    
    # Check electron microscopy variants
    for variant in _ELECTRON_MICROSCOPY_VARIANTS:
        if variant in val or val in variant:
            return "Electron Microscopy"
    
    # Check optical microscopy variants
    for _variant in _OPTICAL_MICROSCOPY_VARIANTS:
        if _variant in val or val in _variant:
            return "Optical Microscopy"
    
    # Fallback: if contains "electr" or "électr" → electron, if contains "opti" or "phase" → optical
    if any(kw in val for kw in ["electr", "électr", "elektr"]):
        return "Electron Microscopy"
    if any(kw in val for kw in ["opti", "phase", "contrast", "licht"]):
        return "Optical Microscopy"
    
    # If truly unrecognized, return None (will show as 'Not specified' in analytics)
    return None


def _build_prompt(file_name: str, content: str, language: str) -> str:
    return f"""You are an expert information extraction agent with advanced capabilities in document understanding and structured data generation.

Your task is to analyze the following document and extract relevant information. The document may contain semi-structured or unstructured content. You must interpret, clean, and normalize the data into structured JSON format.

---

**Document Metadata**
- Document name: `{file_name}`
- Language: `{language}`

---

**Document Content (use this to extract data):**

\"\"\"
{content}
\"\"\"

If the document is not in English, first translate it internally (you do not need to show the translated text). Then extract information from the English version.

---

**Your Objective**

Answer the following questions by extracting the corresponding data from the document. If the answer is not explicitly available, use contextual reasoning. If you cannot infer the answer at all, use null for that field.

**Questions to answer for EACH SAMPLE:**
- What is the report number?
- What is the unique sample no/sample code/sample ID/Customer sample reference/Client Reference?
  - (Do not take if it is "Blank" or "Personal" sample)
- What is the pump number or pump location or location sample?
- What is the lab name?
- What is the project name?
- What is the building/factory?
- What is the sample date? (Output in DD/MM/YYYY format)
- What is the analysis method?
  - Only 2 fixed outputs possible: "Optical Microscopy" or "Electron Microscopy".
  - If "Phase Contrast Microscopy" or similar → output "Optical Microscopy".
  - If "Transmission Electron Microscopy" or "Scanning Electron Microscopy" or similar → output "Electron Microscopy".
- What is the followed norm? (e.g., NIOSH 7402, ISO 16000-7, NF X 43-269, HSG 248, VDI 3492)
- What is the volume in litres?
- What is the concentration value for fibres in volume (e.g. /mm3, /L, /cc, etc.)
  - Not values of unit fibres/filter; may be called Result or Analytical Sensitivity
  - concentration may be in format like "<0,010", "<99", "<0.002"
- What is the concentration unit? (e.g. Fibre/L, vezels/cm3, f/m3, etc.)
  - fibres/filter not valid; units may be next to the concentration value in parentheses

---

**Instructions for Output**

Return a JSON object with key "samples" containing an array of objects.
Each sample in the document should be a separate object in the array.
If Sample no is not found but Concentration result is available, still create an entry.

Each object must have these exact keys:
- "Report_number": string or null
- "Sample_no": string or null
- "Pump_Location": string or null
- "Lab_name": string or null
- "Project_Name": string or null
- "Building": string or null
- "Sample_Date": string in DD/MM/YYYY format or null
- "Analysis_method": "Optical Microscopy" or "Electron Microscopy" or null
- "Followed_Norm": string or null
- "Volume": string (in litres) or null
- "Concentration_result": string (preserve "<" prefix if below detection) or null
- "Concentration_unit": string or null

Example output:
{{
  "samples": [
    {{
      "Report_number": "A123X",
      "Sample_no": "S001",
      "Pump_Location": "Office Room 3",
      "Lab_name": "Fibrecount Ltd",
      "Project_Name": null,
      "Building": "Main Building",
      "Sample_Date": "15/03/2026",
      "Analysis_method": "Optical Microscopy",
      "Followed_Norm": "NIOSH 7402",
      "Volume": "480",
      "Concentration_result": "<0.01",
      "Concentration_unit": "f/ml"
    }}
  ]
}}

Return ONLY the JSON object, nothing else."""


# ============================================================
# Content Preparation (mirrors V1 azure_form_recogniser_utils)
# ============================================================

def _format_extraction_content(raw_extraction: dict) -> str:
    """
    Format Document Intelligence output into text content
    exactly as V1 does (paragraphs + tables as pipe-delimited CSV).
    """
    content_parts = []
    
    exclude_roles = {"footnote", "pageHeader", "pageFooter"}
    for para in raw_extraction.get("paragraphs", []):
        role = para.get("role")
        if role not in exclude_roles:
            content_parts.append(para["content"])
    
    for table in raw_extraction.get("tables", []):
        rows = table.get("rows", [])
        if rows:
            for row in rows:
                content_parts.append("|".join(str(cell) for cell in row))
            content_parts.append("")
    
    return "\n".join(content_parts)


def _detect_language(content: str) -> str:
    """Simple language detection based on common patterns."""
    content_lower = content.lower()
    
    if any(w in content_lower for w in ["résultat", "échantillon", "prélèvement", "fibres d"]):
        return "French"
    elif any(w in content_lower for w in ["Ergebnis", "Probe", "Fasern", "Messung"]):
        return "German"
    elif any(w in content_lower for w in ["resultaat", "monster", "vezels", "meting"]):
        return "Dutch"
    elif any(w in content_lower for w in ["resultado", "muestra", "fibras"]):
        return "Spanish"
    return "English"


# ============================================================
# Main Parsing Function
# ============================================================

def parse_extraction(raw_extraction: dict, document_name: str = "") -> list:
    """
    Parse raw Document Intelligence extraction into structured records using LLM.
    Mirrors V1 flow: format content → detect language → GPT prompt → parse response.
    3 retry attempts (same as V1 generic_utils.parse_using_gpt).
    """
    client = _get_openai_client()
    model_name = get_openai_config()["model_name"]
    
    content = _format_extraction_content(raw_extraction)
    
    max_chars = 25000
    if len(content) > max_chars:
        content = content[:max_chars] + "\n[TRUNCATED]"
    
    language = _detect_language(content)
    prompt = _build_prompt(file_name=document_name, content=content, language=language)
    
    # Retry loop (V1 does max 3 attempts)
    records = []
    max_attempts = 3
    
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_completion_tokens=4000,
                response_format={"type": "json_object"}
            )
            
            response_text = response.choices[0].message.content
            parsed = json.loads(response_text)
            
            if isinstance(parsed, dict) and "samples" in parsed:
                records = parsed["samples"]
            elif isinstance(parsed, list):
                records = parsed
            elif isinstance(parsed, dict):
                for key in ("samples", "records", "data", "results"):
                    if key in parsed and isinstance(parsed[key], list):
                        records = parsed[key]
                        break
                else:
                    records = [parsed]
            
            # Validate we got real data
            if records and any(
                r.get("Report_number") or r.get("Sample_no") or r.get("Concentration_result")
                for r in records
            ):
                break
                
        except (json.JSONDecodeError, Exception) as e:
            if attempt == max_attempts:
                raise RuntimeError(f"LLM extraction failed after {max_attempts} attempts: {e}")
            continue
    
    # Enrich records
    for record in records:
        record["Document_name"] = document_name
        
        # Normalize Analysis_method — GPT sometimes returns non-English variants
        record["Analysis_method"] = _normalize_analysis_method(record.get("Analysis_method"))
        
        # Validate Sample_Date
        sample_date = record.get("Sample_Date")
        if sample_date and sample_date not in ("Not specified", None):
            try:
                dt = datetime.strptime(str(sample_date), "%d/%m/%Y")
                if dt.year < 2020:
                    record["_date_warning"] = f"Suspicious date (before 2020): {sample_date}"
            except (ValueError, TypeError):
                record["_date_warning"] = f"Unexpected date format: {sample_date}"
    
    return records


def convert_concentration_to_f_ml(concentration_result: str, concentration_unit: str) -> str:
    """
    Convert concentration to f/ml (fibers per milliliter).
    Mirrors V1 convert_concentration logic.
    """
    if not concentration_result or not concentration_unit:
        return ""
    
    try:
        result_str = str(concentration_result).replace(",", ".").strip()
        
        less_than = False
        if "<" in result_str:
            less_than = True
            result_str = result_str.replace("<", "").strip()
        
        result = float(result_str)
        unit_lower = concentration_unit.lower()
        
        if any(u in unit_lower for u in ["/m3", "/m³"]):
            result = result / 1000000
        elif any(u in unit_lower for u in ["/l", "/liter", "/litre"]):
            result = result / 1000
        elif any(u in unit_lower for u in ["/ml", "/cm3", "/cm³", "/cc"]):
            result = result
        elif any(u in unit_lower for u in ["/mm3", "/mm³"]):
            result = result * 1000
        else:
            return "Not specified"
        
        formatted = f"{result:.4f}"
        if less_than:
            return f"<{formatted}"
        return formatted
        
    except (ValueError, TypeError):
        return "Not specified"
