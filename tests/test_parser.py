# tests/test_parser.py
import sys
import os
# Ensure we can import from the backend/gis modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gis.cap_parser import parse_cap_xml

def test_parse_valid_cap_xml():
    """Test parsing a minimal, valid CAP XML string."""
    xml_bytes = b"""<?xml version="1.0" encoding="UTF-8"?>
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
        <identifier>TEST-123</identifier>
        <sender>TestAgency</sender>
        <sent>2026-08-24T12:00:00+02:00</sent>
        <info>
            <language>en</language>
            <event>Severe Thunderstorm Warning</event>
            <severity>Severe</severity>
            <urgency>Immediate</urgency>
            <description>Heavy rain and hail expected.</description>
        </info>
    </alert>"""
    
    result = parse_cap_xml(xml_bytes)
    
    assert result is not None
    assert result["identifier"] == "TEST-123"
    assert result["event"] == "Severe Thunderstorm Warning"
    assert result["severity"] == "Severe"

def test_severity_fallback_from_title():
    """Test that if severity is missing, it falls back to the event title (e.g., 'Orange')."""
    xml_bytes = b"""<?xml version="1.0" encoding="UTF-8"?>
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
        <identifier>TEST-456</identifier>
        <sender>TestAgency</sender>
        <sent>2026-08-24T12:00:00+02:00</sent>
        <info>
            <language>en</language>
            <event>Orange Rain Warning issued for Region X</event>
            <!-- Severity tag intentionally omitted to test fallback -->
            <urgency>Expected</urgency>
            <description>Heavy rain expected.</description>
        </info>
    </alert>"""
    
    result = parse_cap_xml(xml_bytes)
    
    assert result is not None
    # The parser should see "Orange" in the title and assign "Severe"
    assert result["severity"] == "Severe"