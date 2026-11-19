"""Clear a participant's clips and labels so that annotation can start afresh.

    uv run python reset.py                 the participant named in local.toml
    uv run python reset.py Pxx             another participant folder
    uv run python reset.py --recording     also forget what was read from the videos
    uv run python reset.py --rater         also forget the rater's name
    uv run python reset.py --yes           do not ask before doing it

Clips, segments.csv and design.toml are deleted. Annotation files are not
deleted: they are moved to data4annotation/_archive/. Stop the app first.
All the logic is in parkour/reset.py.
"""

import argparse
import sys

from parkour import config, reset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("subject", nargs="?", help="participant folder; default: the one in local.toml")
    parser.add_argument("--recording", action="store_true",
                        help="also delete the saved read of the source videos")
    parser.add_argument("--rater", action="store_true",
                        help="also remove the rater's name from local.toml")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args()

    subject = args.subject or (config.load_local() or {}).get("subject")
    if not subject:
        print("No participant given, and local.toml names none.")
        return 1

    found = reset.plan(subject, recording=args.recording, rater=args.rater)
    if found.empty:
        print(f"Nothing to clear for {subject}.")
        return 0

    print(f"Reset of {subject}:\n")
    print("\n".join(found.lines()))
    if not args.yes:
        try:
            typed = input(f"\nType the participant's name ({subject}) to go ahead: ")
        except EOFError:            # nobody at the keyboard
            typed = ""
        if typed.strip() != subject:
            print("Nothing was changed.")
            return 1
    reset.apply(found)
    print("\nDone. Start the app to generate clips and annotate afresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
