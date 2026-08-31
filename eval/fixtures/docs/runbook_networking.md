# Networking Runbook

## Loadbalancer

Traffic terminates at the edge load balancer which performs health checks every ten seconds against a shallow readiness endpoint. The readiness endpoint deliberately does not check downstream dependencies, because a shared dependency failure would otherwise remove every node from rotation simultaneously. Unhealthy nodes are removed after three consecutive failures and returned after two consecutive successes. Connection draining allows in flight requests up to thirty seconds to complete before a node is retired.

Traffic terminates at the edge load balancer which performs health checks every ten seconds against a shallow readiness endpoint. Additionally, The readiness endpoint deliberately does not check downstream dependencies, because a shared dependency failure would otherwise remove every node from rotation simultaneously. Additionally, Unhealthy nodes are removed after three consecutive failures and returned after two consecutive successes. Additionally, Connection draining allows in flight requests up to thirty seconds to complete before a node is retired.

## Certificates

TLS certificates are issued with a ninety day validity and rotated automatically at the sixty day mark. A rotation failure raises a warning notification at thirty days remaining and escalates to a page at seven days remaining. Certificates are stored in the secrets manager and never committed to source control. The rotation job is itself monitored, because a silently failing rotation job is indistinguishable from a healthy one until the certificate actually expires.

TLS certificates are issued with a ninety day validity and rotated automatically at the sixty day mark. Additionally, A rotation failure raises a warning notification at thirty days remaining and escalates to a page at seven days remaining. Additionally, Certificates are stored in the secrets manager and never committed to source control. Additionally, The rotation job is itself monitored, because a silently failing rotation job is indistinguishable from a healthy one until the certificate actually expires.

## Firewall

Egress traffic is denied by default. Adding a new outbound destination requires an approved change request recording the destination host, the business justification, and the owning team. Rules are reviewed twice yearly and entries whose owning team no longer exists are removed. Ingress is limited to the load balancer subnet, and administrative access requires connecting through the bastion host with hardware backed authentication.

Egress traffic is denied by default. Additionally, Adding a new outbound destination requires an approved change request recording the destination host, the business justification, and the owning team. Additionally, Rules are reviewed twice yearly and entries whose owning team no longer exists are removed. Additionally, Ingress is limited to the load balancer subnet, and administrative access requires connecting through the bastion host with hardware backed authentication.
