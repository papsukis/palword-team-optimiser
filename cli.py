from __future__ import annotations

import argparse

from data_loader import (
    load_pals,
    load_partner_skills,
    load_buff_graph,
    load_status_engine,
    load_mount_engine,
)
from engine import score_team


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a Palworld elemental team.")
    parser.add_argument("--element", required=True)
    parser.add_argument("--team", nargs="+", required=True, help="Pal names")
    args = parser.parse_args()

    result = score_team(
        args.team,
        args.element,
        load_pals(),
        load_partner_skills(),
        load_buff_graph(),
        load_status_engine(),
        load_mount_engine(),
    )

    print(f"Overall score: {result.overall:.1f}%")
    for key, value in result.to_dict().items():
        if key != "notes":
            print(f"{key}: {value}")
    print("Notes:")
    for note in result.notes:
        print(f"- {note}")


if __name__ == "__main__":
    main()
