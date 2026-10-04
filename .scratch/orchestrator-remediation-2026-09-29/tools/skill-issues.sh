#!/usr/bin/env bash
# skill-issues.sh <doc.md>
# Prints the skill-issue list from the doc itself: each A-I entry's heading and its first paragraph,
# cut to 260 characters. A list I give you is this output, not text typed from memory.
awk '
  /^### [A-I]\./ { sec = $0; next }
  /^#### [A-I][0-9]+\./ { h = $0; c = 0; print "\n" h; next }
  /^##/ { h = ""; next }
  h != "" && NF && c < 1 && !/^\|/ && !/^```/ { print "  " substr($0, 1, 260); c++ }
' "${1:?doc}"
