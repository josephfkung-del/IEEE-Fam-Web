"""Preserve the deployed application and apply submission reliability fixes."""
from baseline_entry import app
from submission_reliability import install

install(app)
