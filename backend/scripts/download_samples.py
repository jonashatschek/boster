"""Download the sample cooperative documents used by the regression tests.

The PDFs are public documents published by each cooperative, but they are not
committed to the repository. Run this once: python -m scripts.download_samples
"""

from pathlib import Path

import httpx

SAMPLE_DIRECTORY = Path(__file__).parents[2] / "sample_documents"

SAMPLES = {
    "segelflygaren_arsredovisning.pdf":
        "https://documents.bcdn.se/d8/f0/74acbba508b6/DOK5PWMDF42M7X3T8QG46.pdf",
    "friheten_arsredovisning_2024-2025.pdf":
        "https://documents.bcdn.se/28/dc/ef4a1bdecefd/arsredovisning-2024-2025.pdf",
    "sannadalsplatan_arsredovisning.pdf":
        "https://documents.bcdn.se/dd/8c/436a211d7d05/F_ORG_T493_139907.pdf",
    "byamannen_ekonomisk_plan_2025.pdf":
        "https://documents.bcdn.se/27/e8/7d889bd4c2c1/Ekonomisk-plan-2025.pdf",
    "byamannen2_arsredovisning_2025.pdf":
        "https://documents.bcdn.se/b3/8d/cdcd074b833d/brf_byamannen_2_769616-5187_-_signerad_arsredovisning_2025_1.pdf",
    "soderbysjon_arsredovisning.pdf":
        "https://documents.bcdn.se/59/61/a041d9d7334f/360159.pdf",
    "702002-3532_arsredovisning.pdf":
        "https://documents.bcdn.se/a5/1f/2ace0062c08c/702002-3532.pdf",
}


def main() -> None:
    SAMPLE_DIRECTORY.mkdir(exist_ok=True)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for filename, url in SAMPLES.items():
            target = SAMPLE_DIRECTORY / filename
            if target.exists():
                print(f"exists      {filename}")
                continue
            response = client.get(url)
            response.raise_for_status()
            target.write_bytes(response.content)
            print(f"downloaded  {filename} ({len(response.content) // 1024} kB)")


if __name__ == "__main__":
    main()
