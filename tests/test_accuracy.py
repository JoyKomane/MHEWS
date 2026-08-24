# tests/test_accuracy.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gis.accuracy import compute_accuracy, polygon_wkt_to_shapely

def test_valid_polygon_accuracy():
    """Test that a valid, slightly irregular polygon gets a reasonable precision score."""
    # A simple triangle-like polygon
    wkt = "POLYGON((30.0 -23.4, 31.2 -23.4, 30.6 -24.2, 30.0 -23.4))"
    score = compute_accuracy(wkt)
    
    # Should return an integer between 0 and 100
    assert isinstance(score, int)
    assert 0 <= score <= 100

def test_invalid_wkt_accuracy():
    """Test that completely invalid WKT returns 0 (or a safe fallback)."""
    invalid_wkt = "NOT A VALID POLYGON STRING"
    score = compute_accuracy(invalid_wkt)
    
    assert score == 0