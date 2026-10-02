"""Run the support agent on a single message.

    python main.py --sender "Hina Qureshi" --message "Where is order A-37?"
    python main.py                      # interactive
"""
import argparse

from dotenv import load_dotenv

from agent.loop import run_agent


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--sender")
    ap.add_argument("--message")
    args = ap.parse_args()
    sender = args.sender or input("Sender name: ")
    message = args.message if args.message is not None else input("Customer message: ")

    result = run_agent(message, sender)
    print("\n" + "=" * 60 + "\nFINAL REPLY\n" + "=" * 60)
    print(result["final_text"])
    if result["draft"] and result["draft"]["escalate"]:
        print("\n[ESCALATED] handover note:", result["draft"]["handover_note"])
    print("=" * 60)
    print(f"stop_reason={result['stop_reason']}  cost=${result['cumulative_cost_usd']:.5f}")
    print(f"full trace: {result['log_path']}")


if __name__ == "__main__":
    main()
