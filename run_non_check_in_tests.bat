@echo off
SET SHELL_CMD=python -m unittest discover -v --start-directory=./tests/non_check_in_gating_tests/all_exchanges --pattern=test_*.py
echo %SHELL_CMD%
%SHELL_CMD%

SET SHELL_CMD=python -m unittest discover -v --start-directory=./tests/non_check_in_gating_tests/all_exchanges --pattern=ut_*.py
echo %SHELL_CMD%
%SHELL_CMD%