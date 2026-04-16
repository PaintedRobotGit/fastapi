# Database Schema

Marketing management SaaS. Partners are agencies that purchase the platform; Customers are client accounts belonging to a Partner. Users belong to either a Partner or a Customer — or neither (admin-tier users). All timestamps stored in UTC as `TIMESTAMPTZ`.

**Database:** PostgreSQL (Railway)

---

## Tables

### `partners`
Agency accounts that purchase and manage the platform.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `name` | `varchar(255)` | NO | | |
| `email` | `varchar(255)` | YES | | Primary contact email |
| `slug` | `varchar(100)` | YES | | URL-friendly identifier — unique |
| `plan` | `varchar(50)` | NO | `'trial'` | `trial`, `starter`, `pro`, `enterprise` |
| `timezone` | `varchar(100)` | NO | `'UTC'` | IANA timezone string |
| `is_active` | `boolean` | NO | `true` | |
| `trial_ends_at` | `timestamptz` | YES | | |
| `subscription_expires_at` | `timestamptz` | YES | | |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `slug` unique

---

### `customers`
Client accounts owned by a Partner.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` (cascade delete) |
| `name` | `varchar(255)` | NO | | |
| `email` | `varchar(255)` | YES | | Primary contact email |
| `industry` | `varchar(100)` | YES | | |
| `timezone` | `varchar(100)` | NO | `'UTC'` | IANA timezone string |
| `is_active` | `boolean` | NO | `true` | |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `customers_partner_id_fkey` → `partners.id` ON DELETE CASCADE  
**Indexes:** `idx_customers_partner_id` on `partner_id`

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
| `role_id` | `integer` | NO | | FK → `roles.id` |
| `is_active` | `boolean` | NO | `true` | |
| `is_verified` | `boolean` | NO | `false` | |
| `partner_id` | `integer` | YES | | FK → `partners.id` — mutually exclusive with `customer_id` |
| `customer_id` | `integer` | YES | | FK → `customers.id` — mutually exclusive with `partner_id` |
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
- `users_partner_id_fkey` → `partners.id` ON DELETE SET NULL
- `users_customer_id_fkey` → `customers.id` ON DELETE SET NULL
- `users_role_id_fkey` → `roles.id` ON DELETE SET NULL

---

### `roles`
Defines the available roles per tier. Roles are seeded — not user-created.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `name` | `varchar(50)` | NO | | Unique. e.g. `partner_owner` |
| `tier` | `varchar(20)` | NO | | `admin`, `partner`, or `customer` |
| `description` | `text` | YES | | |
| `is_default` | `boolean` | NO | `false` | Default role assigned for that tier on signup |
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

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | `serial` | NO | PK |
| `key` | `varchar(100)` | NO | Unique. e.g. `partner_customers:create` |
| `description` | `text` | YES | |
| `created_at` | `timestamptz` | NO | |

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
| `role_id` | `integer` | NO | PK, FK → `roles.id` (cascade delete) |
| `permission_id` | `integer` | NO | PK, FK → `permissions.id` (cascade delete) |

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

## Relationships

```
partners
  └── customers        (partner_id → partners.id)
  └── users            (partner_id → partners.id)

customers
  └── users            (customer_id → customers.id)

roles
  └── users            (role_id → roles.id)
  └── role_permissions (role_id → roles.id)

permissions
  └── role_permissions (permission_id → permissions.id)
```
