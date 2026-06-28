import pytest
from cvrsvs_validator import Member, GovernanceError, validate_cvrsvs_honorvm

def test_quaestor_valid():
    member = Member("Valid Quaestor", 2000)
    # At year 2030, age is 30.
    assert validate_cvrsvs_honorvm(member, "quaestor", 2030) is True

def test_quaestor_too_young():
    member = Member("Young", 2000)
    # At year 2029, age is 29.
    with pytest.raises(GovernanceError, match="Minimum 30 required for Quaestor"):
        validate_cvrsvs_honorvm(member, "quaestor", 2029)

def test_praetor_valid():
    member = Member("Valid Praetor", 2000)
    member.add_office("quaestor", 2030, 2031)
    assert validate_cvrsvs_honorvm(member, "praetor", 2039) is True

def test_praetor_missing_quaestor():
    member = Member("No Quaestor", 2000)
    with pytest.raises(GovernanceError, match="must hold Quaestor before advancing to Praetor"):
        validate_cvrsvs_honorvm(member, "praetor", 2039)

def test_consul_valid():
    member = Member("Valid Consul", 2000)
    member.add_office("quaestor", 2030, 2031)
    member.add_office("praetor", 2039, 2040)
    assert validate_cvrsvs_honorvm(member, "consul", 2042) is True

def test_consul_missing_praetor():
    member = Member("No Praetor", 2000)
    member.add_office("quaestor", 2030, 2031)
    with pytest.raises(GovernanceError, match="must hold Praetor before advancing to Consul"):
        validate_cvrsvs_honorvm(member, "consul", 2042)

def test_censor_valid():
    member = Member("Valid Censor", 2000)
    member.add_office("quaestor", 2030, 2031)
    member.add_office("praetor", 2039, 2040)
    member.add_office("consul", 2042, 2043)
    assert validate_cvrsvs_honorvm(member, "censor", 2045) is True

def test_gap_rule_violation():
    member = Member("Gap Violator", 2000)
    member.add_office("quaestor", 2030, 2031)
    member.add_office("praetor", 2039, 2040)
    member.add_office("consul", 2042, 2043)
    
    # Try to hold consul again only 5 years later (gap is 2048 - 2043 = 5 < 10)
    with pytest.raises(GovernanceError, match="10-year gap is required"):
        validate_cvrsvs_honorvm(member, "consul", 2048)

def test_gap_rule_valid():
    member = Member("Gap Follower", 2000)
    member.add_office("quaestor", 2030, 2031)
    member.add_office("praetor", 2039, 2040)
    member.add_office("consul", 2042, 2043)
    
    # Try to hold consul again 10 years later (gap is 2053 - 2043 = 10)
    assert validate_cvrsvs_honorvm(member, "consul", 2053) is True
