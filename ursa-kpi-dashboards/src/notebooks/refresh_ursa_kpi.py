import argparse
import sys
from pathlib import Path

from pyspark.sql import SparkSession


def main():
    parser = argparse.ArgumentParser()
    for name in ("catalog", "source-catalog", "target", "config-path"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--mode", required=True, choices=("preflight", "materialize", "verify"))
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.config_path).parent))

    from ursa_runtime import execute

    spark = SparkSession.builder.getOrCreate()
    execute(spark, args.config_path, args.catalog, args.source_catalog, args.target, args.mode)


if __name__ == "__main__":
    main()