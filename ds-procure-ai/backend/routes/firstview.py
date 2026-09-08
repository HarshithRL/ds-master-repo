from flask import Blueprint, jsonify

firstview_bp = Blueprint("firstview", __name__)


@firstview_bp.route("/api/firstview", methods=["GET"])
def firstview():
    return jsonify({
        "page": "firstview",

        "brand": {
            "name": "Mate",
            "logo": "/etex-logo.png"
        },

        "welcome": {
            "greeting": "Evening Harshith,",
            "description": (
                "Start a new chat, generate meeting notes, "
                "or build documents — all powered by AI "
                "to make your work easier."
            )
        },

        "categories": [
            {
                "name": "General",
                "tools": [
                    {
                        "name": "Chat",
                        "description": "Ask questions, generate insights, and receive AI-powered support to enhance your work.",
                        "icon": "chat",
                        "path": "/app/chat"
                    },
                    {
                        "name": "Meeting Summarizer",
                        "description": "Convert discussions into structured meeting notes with AI-generated summaries.",
                        "icon": "meeting",
                        "path": "/app/meeting-summarizer"
                    },
                    {
                        "name": "Document Builder",
                        "description": "Create, merge and edit documents or code instantly with AI-driven precision.",
                        "icon": "document",
                        "path": "/app/document-builder"
                    },
                    {
                        "name": "Document Translator",
                        "description": "Translate texts & full document files instantly while preserving the format.",
                        "icon": "translate",
                        "path": "/app/document-translator"
                    },
                    {
                        "name": "Scope Builder",
                        "description": "Transforming raw requirements into actionable user stories, instantly.",
                        "icon": "scope",
                        "path": "/app/scope-builder"
                    }
                ]
            }
        ]
    })