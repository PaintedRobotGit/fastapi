# Database Schema

Marketing management SaaS. Partners are agencies that purchase the platform; Customers are client accounts belonging to a Partner. Users belong to either a Partner or a Customer — never both.

**Database:** PostgreSQL (Railway) — all timestamps stored in UTC as `TIMESTAMPTZ`.

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
| `plan` | `varchar(50)` | NO | `'trial'` | e.g. `trial`, `starter`, `pro`, `enterprise` |
| `timezone` | `varchar(100)` | NO | `'UTC'` | IANA timezone string |
| `is_active` | `boolean` | NO | `true` | |
| `trial_ends_at` | `timestamptz` | YES | | |
| `subscription_expires_at` | `timestamptz` | YES | | |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:**
- `partners_slug_key` — `slug` is unique

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

**Constraints:**
- `customers_partner_id_fkey` — FK → `partners.id` ON DELETE CASCADE

**Indexes:**
- `idx_customers_partner_id` on `partner_id`

---

### `users`
Individuals who log in. Must belong to exactly one Partner or one Customer.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `email` | `varchar(255)` | NO | | Unique |
| `username` | `varchar(50)` | YES | | Unique |
| `password_hash` | `varchar(255)` | YES | | Null for OAuth users |
| `first_name` | `varchar(100)` | YES | | |
| `last_name` | `varchar(100)` | YES | | |
| `avatar_url` | `varchar(512)` | YES | | |
| `role` | `varchar(50)` | NO | `'user'` | |
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
- `users_email_key` — `email` is unique
- `users_username_key` — `username` is unique
- `uq_provider_account` — `(auth_provider, provider_id)` is unique
- `chk_user_account_exclusive` — `num_nonnulls(partner_id, customer_id) = 1` (exactly one must be set)
- `users_partner_id_fkey` — FK → `partners.id` ON DELETE SET NULL
- `users_customer_id_fkey` — FK → `customers.id` ON DELETE SET NULL

---

## Relationships

```
partners
  └── customers (partner_id → partners.id)
  └── users     (partner_id → partners.id)

customers
  └── users     (customer_id → customers.id)
```
