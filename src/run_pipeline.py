from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    "src/prepare_fire_perimeters.py",
    "src/extract_gee_timeseries.py",
    "src/build_analysis_dataset.py",
    "src/analyze_recovery.py",
    "src/generate_final_figures.py",
]


def main() -> None:
    for step in STEPS:
        print(f"\n==> {step}")
        subprocess.run([sys.executable, step], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
