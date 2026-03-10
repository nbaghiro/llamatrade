#!/usr/bin/env bash
#
# Check for lint/type suppression comments that should be avoided.
# These bypass our quality checks and should be fixed at the root cause.
#
# Usage: ./scripts/check-no-suppressions.sh
#
# Checks for:
#   - # noqa (ruff suppression - handled by --ignore-noqa but belt-and-suspenders)
#   - # type: ignore (type checker suppression)
#   - # pyright: (pyright directive to disable rules)
#
# Exit codes:
#   0 - No suppressions found
#   1 - Suppressions found

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Directories to check
DIRS="services/ libs/"

# Patterns to check (excluding generated code)
EXCLUDE_PATTERN="libs/proto/llamatrade_proto/generated"

echo "Checking for lint/type suppression comments..."

FOUND=0

# Check for # noqa
if grep -rn "# noqa" $DIRS --include="*.py" 2>/dev/null | grep -v "$EXCLUDE_PATTERN"; then
    echo -e "${RED}Found # noqa comments. Remove them and fix the underlying lint issue.${NC}"
    FOUND=1
fi

# Check for # type: ignore
if grep -rn "# type: ignore" $DIRS --include="*.py" 2>/dev/null | grep -v "$EXCLUDE_PATTERN"; then
    echo -e "${RED}Found # type: ignore comments. Remove them and fix the underlying type issue.${NC}"
    FOUND=1
fi

# Check for # pyright: directives
if grep -rn "# pyright:" $DIRS --include="*.py" 2>/dev/null | grep -v "$EXCLUDE_PATTERN"; then
    echo -e "${RED}Found # pyright: directives. Remove them and fix the underlying type issue.${NC}"
    FOUND=1
fi

if [ $FOUND -eq 1 ]; then
    echo ""
    echo -e "${RED}Suppression comments found! Fix the underlying issues instead of suppressing them.${NC}"
    exit 1
else
    echo -e "${GREEN}No suppression comments found.${NC}"
    exit 0
fi
