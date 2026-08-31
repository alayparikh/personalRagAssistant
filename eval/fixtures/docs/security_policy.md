# Security Policy

## Accessreview

Access to production systems is reviewed every quarter by the owning team lead. Any account that has not authenticated in ninety days is disabled automatically. Break glass credentials are stored in the secrets manager, and every retrieval is logged and reviewed on the next business day. Reviews cover service accounts as well as human accounts, since orphaned service accounts are a common and easily overlooked risk.

Access to production systems is reviewed every quarter by the owning team lead. Additionally, Any account that has not authenticated in ninety days is disabled automatically. Additionally, Break glass credentials are stored in the secrets manager, and every retrieval is logged and reviewed on the next business day. Additionally, Reviews cover service accounts as well as human accounts, since orphaned service accounts are a common and easily overlooked risk.

## Dependencies

Dependencies are scanned daily against published vulnerability databases. Critical severity findings must be remediated within seven days and high severity findings within thirty days. Automated pull requests are opened for patch level upgrades and are merged once the pipeline passes. Major version upgrades are scheduled deliberately because they frequently carry behavioural changes that the test suite may not fully cover.

Dependencies are scanned daily against published vulnerability databases. Additionally, Critical severity findings must be remediated within seven days and high severity findings within thirty days. Additionally, Automated pull requests are opened for patch level upgrades and are merged once the pipeline passes. Additionally, Major version upgrades are scheduled deliberately because they frequently carry behavioural changes that the test suite may not fully cover.

## Classification

Data is classified as public, internal, confidential, or restricted. Restricted data may not leave the production environment and may never be copied into development or staging systems under any circumstances, including for the purpose of reproducing a bug. When a production issue requires realistic data, an anonymisation job produces a synthetic dataset preserving the shape of the original without the sensitive values.

Data is classified as public, internal, confidential, or restricted. Additionally, Restricted data may not leave the production environment and may never be copied into development or staging systems under any circumstances, including for the purpose of reproducing a bug. Additionally, When a production issue requires realistic data, an anonymisation job produces a synthetic dataset preserving the shape of the original without the sensitive values.
