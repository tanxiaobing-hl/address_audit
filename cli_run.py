from __future__ import annotations
from pathlib import Path
from address_audit.config import load_config
from address_audit.pipeline import AddressGovernancePipeline

import dotenv
dotenv.load_dotenv()

def main():
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    cfg = load_config(data_dir / "config.default.json")

    pipe = AddressGovernancePipeline(cfg, str(data_dir))
    result = pipe.run()
    print("Pipeline finished:", result)
    print("Excel 数据位于:", cfg.db_path)

if __name__ == "__main__":
    main()
