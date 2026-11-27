#!/usr/bin/env bash
# Restrict outbound traffic of the sandbox VM to the hosts in allowlist.txt.
# Run INSIDE the VM as root (vm.sh does this on every start):
#
#   sudo /workspace/sandbox/egress.sh /workspace/sandbox/allowlist.txt [ollama-port]
#
# Method: resolve each allowed host to its current addresses, allow those plus
# DNS, drop the rest. Addresses of large services rotate, so this runs again on
# every VM start. It filters by address, not by hostname: a host that shares an
# address with an allowed one is reachable too. Docker Sandboxes' proxy filters
# by hostname and is the stricter option.
#
# NOT YET TESTED on a Mac. Run docs/redteam-checklist.md after first setup.
set -euo pipefail

allowlist="${1:?usage: egress.sh <allowlist.txt> [ollama-port]}"
ollama_port="${2:-11434}"

ipset create allowed hash:ip -exist
ipset flush allowed

while IFS= read -r line; do
  host="${line%%#*}"
  host="$(echo "$host" | tr -d '[:space:]')"
  [ -z "$host" ] && continue
  for ip in $(dig +short A "$host" | grep -E '^[0-9.]+$' || true); do
    ipset add allowed "$ip" -exist
  done
done < "$allowlist"

gateway="$(ip route | awk '/default/ {print $3; exit}')"

iptables -F OUTPUT
iptables -P OUTPUT DROP
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
# Ollama on the host, and nothing else on the host.
iptables -A OUTPUT -d "$gateway" -p tcp --dport "$ollama_port" -j ACCEPT
iptables -A OUTPUT -p tcp -m multiport --dports 80,443 -m set --match-set allowed dst -j ACCEPT
iptables -A OUTPUT -j REJECT

ip6tables -F OUTPUT
ip6tables -P OUTPUT DROP
ip6tables -A OUTPUT -o lo -j ACCEPT

echo "egress limited to $(ipset list allowed | grep -cE '^[0-9]') addresses from $allowlist"
