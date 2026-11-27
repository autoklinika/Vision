"""Local seat0 approval for a manual session, not a drive command."""
import argparse
from .nero_clear import valid_id
from .nero_local_approval import Approval,local_console

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",required=True,help="Dedicated manual approval directory, never the diagnostic clear directory")
    p.add_argument("operation")
    a=p.parse_args()
    if not valid_id(a.operation) or not local_console():p.error("active local console required")
    if input("Confirm supervised manual NERO session; type ENABLE: ").strip()!="ENABLE" or not local_console():
        p.error("confirmation rejected")
    Approval(a.directory).grant(a.operation,255)
    print("One-use approval granted for 60 s. No hardware command was sent.")

if __name__=="__main__":main()
