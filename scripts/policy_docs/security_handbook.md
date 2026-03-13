# Apex Technologies — Information Security Handbook
**Document ID:** SEC-POL-003  
**Version:** 4.0  
**Effective Date:** February 1, 2025  
**Owner:** Chief Information Security Officer  
**Classification:** Internal Use Only

---

## 1. Access Control

### 1.1 Principle of Least Privilege
All system access must be provisioned on a least-privilege basis — employees receive only the permissions required to perform their current job function. Access reviews are conducted quarterly. Granting broad administrative access to expedite a project is a security policy violation. Production database access may not be granted to developers without CISO approval and must be time-limited.

### 1.2 Multi-Factor Authentication
MFA is mandatory for all Apex systems accessible from outside the corporate network, including AWS, GitHub, Jira, Salesforce, and all SaaS tools. Disabling MFA for any production system or individual account — even temporarily for troubleshooting — requires written CISO approval. Accounts found without MFA will be suspended within 24 hours.

### 1.3 Privileged Access Management
All privileged credentials (root accounts, service account keys, API tokens with admin scope) must be stored in the approved secrets manager (HashiCorp Vault or AWS Secrets Manager). Hardcoding credentials in source code, configuration files, or environment variables committed to version control is a critical security violation. Automated scanning is in place — violations trigger immediate incident response.

### 1.4 Offboarding
IT and HR must execute the offboarding checklist within 2 hours of an employee's last working moment. This includes revoking all SSO access, recovering company devices, rotating any shared credentials the employee had access to, and removing SSH keys from all systems. Delayed offboarding of employees terminated for cause is a high-severity security risk.

---

## 2. Data Security

### 2.1 Data Classification
Apex data is classified into four tiers: Public, Internal, Confidential, and Restricted. Customer PII, financial records, and authentication credentials are Restricted. Restricted data must be encrypted at rest (AES-256) and in transit (TLS 1.2 minimum). Storing Restricted data in unencrypted form — including in Slack messages, email attachments, or local unencrypted drives — is prohibited.

### 2.2 Encryption Standards
All new services must implement TLS 1.3 for data in transit. TLS 1.0 and 1.1 are deprecated and must not be used. Encryption keys must be rotated annually and managed through the approved KMS. Customer-managed encryption keys (CMEK) are required for all Restricted data stored in cloud services. Using default cloud provider encryption without CMEK for Restricted data does not meet Apex's compliance requirements.

### 2.3 Database Security
Production databases must not be publicly accessible. All database connections must go through a VPC with security groups limiting access to application tier only. Direct developer access to production databases is prohibited in normal operations. Any production query run for debugging must be logged, reviewed by a second engineer, and documented in the incident log.

### 2.4 Backup and Recovery
All production data must be backed up daily with a minimum 30-day retention. Backups must be tested for restorability quarterly. Backup data is subject to the same classification and encryption requirements as primary data. Storing backup data in a different region than primary data is required for disaster recovery compliance.

---

## 3. Application Security

### 3.1 Secure Development Lifecycle (SDL)
All features that handle user authentication, payment processing, PII, or privileged operations must undergo a security review before shipping to production. Shipping these feature categories without a security review sign-off is a policy violation. The Security team SLA for reviews is 5 business days — plan accordingly.

### 3.2 Penetration Testing
External penetration tests must be conducted annually on all customer-facing products. Findings rated Critical or High must be remediated within 30 days of the report. Medium findings must be remediated within 90 days. Carrying unpatched Critical vulnerabilities beyond 30 days without a documented exception approved by the CISO is a compliance failure.

### 3.3 Dependency Management
All third-party libraries and dependencies must be scanned for known vulnerabilities before merging to main. Deploying code with a CVSS score ≥ 9.0 (Critical) vulnerability in a dependency is prohibited. Automated vulnerability scanning is integrated in CI/CD — builds will fail on Critical findings. Bypassing the security gate in CI/CD requires written CISO approval.

### 3.4 API Security
All external-facing APIs must implement rate limiting, input validation, and authentication. API keys must never be returned in full after initial creation — only the last 4 characters may be displayed. Public APIs must be protected by WAF (Web Application Firewall). Launching a public API without WAF protection requires a documented risk acceptance signed by the CISO.

---

## 4. Infrastructure Security

### 4.1 Cloud Security Posture
All AWS accounts must have CloudTrail enabled in all regions, GuardDuty active, and Security Hub configured with the AWS Foundational Security Best Practices standard. Disabling any of these services — even temporarily — requires a Change Advisory Board (CAB) approval. New AWS accounts must be provisioned through the Organization management account and enrolled in the security baseline within 24 hours.

### 4.2 Network Segmentation
Production, staging, and development environments must be in separate VPCs with no direct peering between production and development. Security groups must follow a deny-by-default model. Opening port 22 (SSH) or port 3389 (RDP) to 0.0.0.0/0 on any production resource is a critical violation and will trigger an automated remediation that closes the port within 15 minutes.

### 4.3 Container and Serverless Security
Container images must be scanned for vulnerabilities before deployment. Base images must be updated monthly. Lambda functions must not use wildcard IAM permissions (*). Each Lambda must have a dedicated execution role with only the permissions it requires. Lambda environment variables must not contain plaintext secrets — all secrets must be retrieved from Secrets Manager at runtime.

### 4.4 Incident Response
Any suspected security incident must be reported to security@apextech.com within 1 hour of discovery. The Incident Response team will open a Severity-1 bridge call within 30 minutes. During an active incident, only the Incident Commander may communicate externally about the incident — individual employees may not notify customers, partners, or media without authorization. Post-incident reviews are mandatory for all Severity-1 and Severity-2 incidents.

---

## 5. Acceptable Use

### 5.1 Company Devices
Company-owned devices must have full-disk encryption enabled, endpoint protection software installed, and automatic OS updates enabled. Employees may not disable endpoint protection software. Installing software not on the approved software list requires IT approval. Company devices may not be used to access competitor systems, perform security research on unauthorized targets, or store personal data in violation of data privacy laws.

### 5.2 AI and Generative AI Tools
Employees may not input Restricted or Confidential data into external AI tools (ChatGPT, Claude, Gemini, etc.) unless those tools have a signed DPA with Apex and data processing agreements ensuring the data is not used for model training. Using AI tools to generate code that handles authentication, encryption, or PII requires Security review before merging. AI-generated code is not exempt from the SDL process.

### 5.3 Shadow IT
Employees may not procure SaaS tools, cloud services, or software subscriptions using personal or corporate credit cards outside of the approved procurement process. Shadow IT tools that access or store company data create unmanaged data leakage risks and will be blocked by network policy upon discovery. Any existing shadow IT tools must be disclosed to IT and Security within 30 days.
