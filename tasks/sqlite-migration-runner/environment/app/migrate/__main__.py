import argparse
import sys

from .runner import MigrationError, status, up


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="migrate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_up = sub.add_parser("up")
    p_up.add_argument("--db", required=True)
    p_up.add_argument("--dir", required=True)
    p_up.add_argument("--target", type=int)
    p_up.add_argument("--allow-out-of-order", action="store_true")
    p_st = sub.add_parser("status")
    p_st.add_argument("--db", required=True)
    p_st.add_argument("--dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "up":
            for version in up(args.db, args.dir, target=args.target,
                              allow_out_of_order=args.allow_out_of_order):
                print(f"applied {version}")
        else:
            for version, name, state in status(args.db, args.dir):
                print(f"{version:>6}  {state:<8} {name}")
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
