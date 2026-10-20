"""Preserve the deployed application and apply submission reliability fixes."""
from baseline_entry import app
from submission_reliability import install

install(app)

from attendance_admin import install as install_attendance
install_attendance(app)
