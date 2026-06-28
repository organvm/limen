import sys
import argparse
from typing import List, Dict, Any

class GovernanceError(Exception):
    """Raised when a governance rule is violated."""
    pass

class OfficeRecord:
    def __init__(self, title: str, start_year: int, end_year: int):
        self.title = title.lower()
        self.start_year = start_year
        self.end_year = end_year

class Member:
    def __init__(self, name: str, inception_year: int):
        self.name = name
        self.inception_year = inception_year
        self.offices: List[OfficeRecord] = []

    def add_office(self, title: str, start_year: int, end_year: int):
        self.offices.append(OfficeRecord(title, start_year, end_year))

def validate_cvrsvs_honorvm(member: Member, target_office: str, nomination_year: int) -> bool:
    """
    Validates a nomination against the Cvrsvs Honorvm rules.
    Operationalizes the conceptual rules into an executable validator.
    
    Rules:
    1. Quaestor: Minimum age (tenure) of 30.
    2. Praetor: Minimum age 39, must have previously held Quaestor.
    3. Consul: Minimum age 42, must have previously held Praetor.
    4. Censor: Must have previously held Consul.
    5. Gap Rule: 10-year minimum gap between holding the same office again.
    """
    target_office = target_office.lower()
    tenure_years = nomination_year - member.inception_year

    # 1. Office-specific requirements
    if target_office == "quaestor":
        if tenure_years < 30:
            raise GovernanceError(f"Member '{member.name}' has {tenure_years} years tenure. Minimum 30 required for Quaestor.")
            
    elif target_office == "praetor":
        if tenure_years < 39:
            raise GovernanceError(f"Member '{member.name}' has {tenure_years} years tenure. Minimum 39 required for Praetor.")
        if not any(o.title == "quaestor" for o in member.offices):
            raise GovernanceError(f"Member '{member.name}' must hold Quaestor before advancing to Praetor.")
            
    elif target_office == "consul":
        if tenure_years < 42:
            raise GovernanceError(f"Member '{member.name}' has {tenure_years} years tenure. Minimum 42 required for Consul.")
        if not any(o.title == "praetor" for o in member.offices):
            raise GovernanceError(f"Member '{member.name}' must hold Praetor before advancing to Consul.")
            
    elif target_office == "censor":
        if not any(o.title == "consul" for o in member.offices):
            raise GovernanceError(f"Member '{member.name}' must hold Consul before advancing to Censor.")
            
    else:
        raise GovernanceError(f"Unknown office: '{target_office}'. Valid offices: quaestor, praetor, consul, censor.")

    # 2. Gap rule (10 years between holding the same office)
    past_same_offices = [o for o in member.offices if o.title == target_office]
    if past_same_offices:
        last_end_year = max(o.end_year for o in past_same_offices)
        gap = nomination_year - last_end_year
        if gap < 10:
            raise GovernanceError(
                f"Member '{member.name}' last held '{target_office}' ending in {last_end_year}. "
                f"A 10-year gap is required (only {gap} years elapsed by {nomination_year})."
            )

    return True

def main():
    parser = argparse.ArgumentParser(description="Validator for Cvrsvs Honorvm rules.")
    parser.add_argument("--name", required=True, help="Name of the member")
    parser.add_argument("--inception", type=int, required=True, help="Inception (birth) year of the member")
    parser.add_argument("--target", required=True, help="Target office (e.g. quaestor, praetor, consul)")
    parser.add_argument("--year", type=int, required=True, help="Year of nomination")
    parser.add_argument("--past-office", action="append", nargs=3, metavar=("TITLE", "START", "END"), 
                        help="Past office record. E.g. --past-office quaestor 2010 2011")
    
    args = parser.parse_args()

    member = Member(args.name, args.inception)
    if args.past_office:
        for title, start, end in args.past_office:
            member.add_office(title, int(start), int(end))

    try:
        validate_cvrsvs_honorvm(member, args.target, args.year)
        print(f"PASS: '{args.name}' is eligible for '{args.target}' in {args.year}.")
        sys.exit(0)
    except GovernanceError as e:
        print(f"FAIL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
