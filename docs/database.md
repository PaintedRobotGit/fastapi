# Database Schema

Marketing management SaaS. Partners are agencies that purchase the platform; Customers are client accounts belonging to a Partner. Users belong to either a Partner or a Customer — or neither (admin-tier users). All timestamps stored in UTC as `TIMESTAMPTZ`.

**Database:** PostgreSQL (Railway)  
**Extensions:** `citext`, `pgcrypto`, `pg_trgm`  
**Triggers:** `set_updated_at()` fires `BEFORE UPDATE` on `partners`, `customers`, `users`, `plans`

---

## Tables

### `plans`
Subscription tiers defining feature limits per partner account.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `name` | `varchar(50)` | NO | | Unique. `trial`, `starter`, `pro`, `enterprise` |
| `monthly_token_limit` | `integer` | YES | | NULL = unlimited (enterprise) |
| `max_customers` | `integer` | YES | | NULL = unlimited |
| `max_users` | `integer` | YES | | NULL = unlimited |
| `price_monthly` | `numeric(10,2)` | YES | | NULL = custom pricing |
| `is_active` | `boolean` | NO | `true` | |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Seeded plans:**

| Name | Token Limit | Max Customers | Max Users | Price/mo |
|------|-------------|---------------|-----------|----------|
| `trial` | 500,000 | 3 | 5 | $0 |
| `starter` | 2,000,000 | 10 | 15 | $49 |
| `pro` | 10,000,000 | 50 | 100 | $149 |
| `enterprise` | Unlimited | Unlimited | Unlimited | Custom |

---

### `industries`
Reference list for categorising customer accounts.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `name` | `text` | NO | | Unique |
| `slug` | `text` | NO | | Unique. URL-friendly identifier |
| `sort_order` | `integer` | NO | `0` | Display order |
| `is_active` | `boolean` | NO | `true` | |
| `created_at` | `timestamptz` | NO | `now()` | |

**Seeded industries:** Retail, Finance, Health & Wellness, Technology, Real Estate, Food & Beverage, Education, Healthcare, Legal, Construction, Manufacturing, Non-Profit, Hospitality & Tourism, Automotive, Professional Services, E-commerce, Media & Entertainment, Other

---

### `partners`
Agency accounts that purchase and manage the platform.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `name` | `varchar(255)` | NO | | |
| `email` | `varchar(255)` | YES | | Primary contact email |
| `slug` | `varchar(100)` | YES | | URL-friendly identifier — unique |
| `plan_id` | `integer` | NO | | FK → `plans.id` ON DELETE SET NULL |
| `timezone` | `varchar(100)` | NO | `'UTC'` | IANA timezone string |
| `status` | `text` | NO | `'active'` | `trial`, `active`, `past_due`, `canceled`, `suspended` |
| `trial_ends_at` | `timestamptz` | YES | | |
| `subscription_expires_at` | `timestamptz` | YES | | |
| `country` | `text` | YES | | |
| `website` | `text` | YES | | |
| `archived_at` | `timestamptz` | YES | | Set when status = `canceled` or `suspended` |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `slug` unique; `partners_status_check` — status IN (trial, active, past_due, canceled, suspended)  
**Indexes:** `idx_partners_status` on `status` WHERE `archived_at IS NULL`

---

### `customers`
Client accounts owned by a Partner.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `name` | `varchar(255)` | NO | | |
| `slug` | `text` | NO | | Auto-generated from name; unique per partner |
| `email` | `varchar(255)` | YES | | Primary contact email |
| `industry_id` | `integer` | YES | | FK → `industries.id` |
| `timezone` | `varchar(100)` | NO | `'UTC'` | IANA timezone string |
| `website_url` | `text` | YES | | |
| `currency` | `text` | NO | `'USD'` | `USD`, `CAD`, `EUR`, `GBP`, `AUD` |
| `customer_type` | `text` | YES | | `lead_gen`, `ecommerce`, `hybrid`, `other` |
| `status` | `text` | NO | `'prep'` | `prep`, `active`, `on_hold`, `archived` |
| `notes` | `text` | YES | | Internal notes |
| `colour` | `text` | YES | | Hex colour code e.g. `#FF5733` — partner-assigned for UI organisation |
| `archived_at` | `timestamptz` | YES | | Set when status = `archived` |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `uq_customer_partner_slug` — `(partner_id, slug)` unique; CHECK on `currency`, `customer_type`, `status`  
**Indexes:**
- `idx_customers_partner_id` on `partner_id`
- `idx_customers_partner_status` on `(partner_id, status)` WHERE `archived_at IS NULL`

---

### `users`
Individuals who log in. Must belong to at most one Partner or one Customer. Admin-tier users have neither set.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `email` | `varchar(255)` | NO | | Unique |
| `username` | `varchar(50)` | YES | | Unique |
| `password_hash` | `varchar(255)` | YES | | Null for OAuth users |
| `first_name` | `varchar(100)` | YES | | |
| `last_name` | `varchar(100)` | YES | | |
| `avatar_url` | `varchar(512)` | YES | | |
| `role_id` | `integer` | NO | | FK → `roles.id` ON DELETE SET NULL |
| `status` | `text` | NO | `'active'` | `active`, `invited`, `suspended`, `deactivated` |
| `email_verified_at` | `timestamptz` | YES | | NULL = not yet verified |
| `mfa_enabled` | `boolean` | NO | `false` | |
| `mfa_secret` | `text` | YES | | TOTP secret; null until MFA enrolled |
| `onboarding_completed_at` | `timestamptz` | YES | | NULL = onboarding not yet completed |
| `partner_id` | `integer` | YES | | FK → `partners.id` ON DELETE SET NULL — mutually exclusive with `customer_id` |
| `customer_id` | `integer` | YES | | FK → `customers.id` ON DELETE SET NULL — mutually exclusive with `partner_id` |
| `auth_provider` | `varchar(50)` | YES | | `'google'`, `'apple'`, or null for email login |
| `provider_id` | `varchar(255)` | YES | | User ID from the OAuth provider |
| `access_token` | `text` | YES | | |
| `refresh_token` | `text` | YES | | |
| `id_token` | `text` | YES | | JWT from provider (Apple/Google) |
| `token_expires_at` | `timestamptz` | YES | | |
| `scope` | `varchar(512)` | YES | | Granted OAuth scopes |
| `last_login` | `timestamptz` | YES | | |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:**
- `users_email_key` — `email` unique
- `users_username_key` — `username` unique
- `uq_provider_account` — `(auth_provider, provider_id)` unique
- `chk_user_account_exclusive` — `num_nonnulls(partner_id, customer_id) <= 1`
- `users_status_check` — status IN (active, invited, suspended, deactivated)

---

### `roles`
Defines the available roles per tier. Roles are seeded — not user-created.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `name` | `varchar(50)` | NO | | Unique. e.g. `partner_owner` |
| `display_name` | `varchar(100)` | YES | | Human-readable label for UI |
| `tier` | `varchar(20)` | NO | | `admin`, `partner`, or `customer` |
| `description` | `text` | YES | | |
| `is_default` | `boolean` | NO | `false` | Default role assigned for that tier on signup |
| `sort_order` | `integer` | NO | `99` | Display order |
| `created_at` | `timestamptz` | NO | `now()` | |

**Seeded roles:**

| Name | Tier | Default |
|------|------|---------|
| `super_admin` | admin | — |
| `admin` | admin | — |
| `partner_owner` | partner | — |
| `partner_admin` | partner | — |
| `partner_member` | partner | ✓ |
| `customer_owner` | customer | — |
| `customer_admin` | customer | — |
| `customer_member` | customer | ✓ |

---

### `permissions`
Granular permission keys using `resource:action` format.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `key` | `varchar(100)` | NO | | Unique. e.g. `partner_customers:create` |
| `description` | `text` | YES | | |
| `created_at` | `timestamptz` | NO | `now()` | |

**Permission keys by scope:**

| Scope | Keys |
|-------|------|
| Global (admin) | `partners:view/create/edit/delete`, `customers:view/create/edit/delete`, `users:view/create/edit/delete`, `billing:view/manage`, `reports:view`, `system:configure` |
| Partner-scoped | `partner_settings:view/edit`, `partner_billing:view/manage`, `partner_users:view/invite/edit/delete`, `partner_customers:view/create/edit/delete`, `partner_reports:view` |
| Customer-scoped | `customer_settings:view/edit`, `customer_users:view/invite/edit/delete`, `customer_reports:view` |

---

### `role_permissions`
Junction table linking roles to their permissions.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `role_id` | `integer` | NO | PK, FK → `roles.id` ON DELETE CASCADE |
| `permission_id` | `integer` | NO | PK, FK → `permissions.id` ON DELETE CASCADE |

**Role permission matrix:**

| Role | Permissions |
|------|-------------|
| `super_admin` | All |
| `admin` | All except `system:configure` |
| `partner_owner` | All partner + customer scoped |
| `partner_admin` | Partner scoped (no `billing:manage`, no `users:delete`) + customer scoped (no `users:delete`) |
| `partner_member` | `partner_customers:view`, `partner_reports:view`, `customer_settings:view`, `customer_users:view`, `customer_reports:view` |
| `customer_owner` | All customer scoped |
| `customer_admin` | Customer scoped (no `users:delete`) |
| `customer_member` | `customer_settings:view`, `customer_users:view`, `customer_reports:view` |

---

### `ai_token_usage`
Per-request AI API usage log. Used for auditing, billing dispute resolution, and per-period aggregation.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `bigserial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | YES | | FK → `customers.id` ON DELETE SET NULL |
| `model` | `varchar(100)` | NO | | e.g. `claude-sonnet-4-6` |
| `input_tokens` | `integer` | NO | | |
| `output_tokens` | `integer` | NO | | |
| `cache_read_tokens` | `integer` | NO | `0` | Anthropic prompt cache read tokens |
| `cache_write_tokens` | `integer` | NO | `0` | Anthropic prompt cache write tokens |
| `total_tokens` | `integer` | YES | generated | `input + output + cache_read + cache_write` (STORED) |
| `feature` | `varchar(100)` | YES | | What triggered the call e.g. `content_generation` |
| `ai_provider` | `text` | NO | `'default'` | e.g. `anthropic`, `openai` |
| `provider_request_id` | `text` | YES | | Request ID returned by the AI provider |
| `estimated_cost_cents` | `integer` | YES | | Cost estimate in cents |
| `billable_period` | `date` | NO | first of current month | Truncated to month for aggregation |
| `user_id` | `integer` | YES | | FK → `users.id` ON DELETE SET NULL — which user triggered the call |
| `created_at` | `timestamptz` | NO | `now()` | |

**Indexes:**
- `idx_ai_token_usage_partner_period` on `(partner_id, billable_period)`
- `idx_ai_token_usage_customer` on `(customer_id, created_at DESC)`
- `idx_ai_token_usage_feature` on `(feature, created_at DESC)`
- `idx_ai_token_usage_user` on `(user_id, created_at DESC)`

---

### `partner_token_balance`
Pre-aggregated monthly token balance per partner. Used for fast limit checking before each AI call.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `partner_id` | `integer` | NO | | PK, FK → `partners.id` ON DELETE CASCADE |
| `billable_period` | `date` | NO | | PK. First day of the billing month |
| `included_tokens` | `bigint` | NO | `0` | Tokens included in partner's plan for this period |
| `tokens_used` | `bigint` | NO | `0` | Running total of tokens consumed |
| `tokens_remaining` | `bigint` | YES | generated | `included_tokens - tokens_used` (STORED) |
| `cap_warned_at` | `timestamptz` | YES | | When the 80% warning was triggered |
| `cap_reached_at` | `timestamptz` | YES | | When the cap was hit; blocks further AI calls |
| `last_updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** PK on `(partner_id, billable_period)`  
**Indexes:**
- `idx_partner_token_balance_partner` on `partner_id`
- `idx_partner_token_balance_capped` on `(partner_id, billable_period)` WHERE `cap_reached_at IS NOT NULL`

---

## Relationships

```
plans
  └── partners               (plan_id → plans.id)

industries
  └── customers              (industry_id → industries.id)

partners
  └── customers              (partner_id → partners.id)
  └── users                  (partner_id → partners.id)
  └── ai_token_usage         (partner_id → partners.id)
  └── partner_token_balance  (partner_id → partners.id)

customers
  └── users                  (customer_id → customers.id)
  └── ai_token_usage         (customer_id → customers.id)

roles
  └── users                  (role_id → roles.id)
  └── role_permissions       (role_id → roles.id)

users
  └── ai_token_usage         (user_id → users.id)

permissions
  └── role_permissions       (permission_id → permissions.id)
```
