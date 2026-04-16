# app.paintedrobot.com — v3.1: Core Schema DDL (Vendor-Neutral)
## Foundation Layers: Platform, Billing, Customer Core, Brand, Strategy, Integrations

**Created:** 2026-04-16
**Supersedes:** v3 (same structure; vendor references removed)
**Scope:** 36 core tables. Content, Analytics, Work Management, Audit layers in v4.
**Stack:** Postgres 16+, FastAPI, JavaScript frontend

---

## Naming Principles

**The app is vendor-neutral.** The schema, UI, and documentation reference generic capabilities rather than specific products:

| Never say | Always say |
|---|---|
| WordPress, Webflow, Shopify | Website / CMS |
| SERanking, Ahrefs, SEMrush | Keyword Research / Keywords |
| GA4, Matomo, Clarity | Analytics / Heatmap |
| CallRail, Twilio | Call Tracking |
| Google Ads, Meta Ads | Paid Advertising / Ads |
| LinkedIn, Instagram, X | Social |
| Klaviyo, Mailchimp | Email Marketing |
| Stripe | Billing Provider |
| Anthropic, OpenAI | AI Provider |

**Internal plumbing** (billing backend, AI backend) is abstracted at the schema level. The specific provider is a configuration concern, not a schema concern. This gives the platform optionality to add or switch providers without migrations.

**Data model stays rich.** Genericizing doesn't mean dumbing down. SEO metrics like search volume, keyword difficulty, and SERP features are universal across keyword providers — keep them. Just don't attribute them to a specific vendor.

---

## 1. Architectural Patterns (Apply to All Tables)

### 1.1 Primary keys

Every table uses `UUID` primary keys. Generated via `gen_random_uuid()`. Tables that have legacy data from the source system keep a `legacy_source_id TEXT` column for migration traceability; drop after integrity validation.

### 1.2 Timestamps

Every table has `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` and `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`. `updated_at` is maintained via a shared trigger.

### 1.3 Tenant scoping

Every tenant-scoped table has `partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE`. Denormalized onto every table even when reachable via FK chain — keeps RLS policies simple and indexes fast.

Customer-scoped tables additionally carry `customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE`.

### 1.4 Row Level Security (RLS)

Every tenant-scoped table has RLS enabled with two policies:

```sql
CREATE POLICY partner_access ON <table>
  FOR ALL
  USING (partner_id = current_setting('app.current_partner_id', true)::uuid)
  WITH CHECK (partner_id = current_setting('app.current_partner_id', true)::uuid);

CREATE POLICY customer_read ON <table>
  FOR SELECT
  USING (
    customer_id = current_setting('app.current_customer_id', true)::uuid
    AND partner_id = current_setting('app.current_partner_id', true)::uuid
  );
```

### 1.5 FastAPI session variable pattern

```python
async def get_scoped_db(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AsyncSession:
    await db.execute(
        text("SET LOCAL app.current_partner_id = :pid"),
        {"pid": str(user.partner_id)},
    )
    if user.user_type == "customer_user":
        await db.execute(
            text("SET LOCAL app.current_customer_id = :cid"),
            {"cid": str(user.customer_id)},
        )
    return db
```

**Critical:** `SET LOCAL` requires being inside a transaction. Use transaction-pool mode (e.g., PgBouncer transaction mode) — never session-pool.

### 1.6 Platform admin bypass

Platform-level operations use a separate Postgres role with `BYPASSRLS`:

```sql
CREATE ROLE app_platform_admin BYPASSRLS;
GRANT USAGE ON SCHEMA public TO app_platform_admin;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_platform_admin;
```

Application code never uses this role for user requests.

### 1.7 Soft deletes

Tenant-scoped core records use `archived_at TIMESTAMPTZ NULL`. Archived = hidden from normal views, preserved for historical integrity. Hard delete only for GDPR / data-export workflows.

### 1.8 External provider abstraction

For two capabilities, the platform integrates with external providers but does not expose them to Partners:

- **Billing provider** — processes subscription billing. Schema refers to `billing_provider` generically; provider-specific IDs stored as opaque strings.
- **AI provider** — processes AI generation. Schema tracks token usage generically; provider is a configuration value.

This allows adding or switching providers without schema migrations.

---

## 2. Platform Layer (Tables 1–6)

### 2.1 `partners`

```sql
CREATE TABLE partners (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name              TEXT NOT NULL,
  slug              TEXT NOT NULL UNIQUE,
  billing_email     CITEXT NOT NULL,
  website           TEXT,
  country           TEXT,
  timezone          TEXT NOT NULL DEFAULT 'UTC',
  status            TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('trial', 'active', 'past_due', 'canceled', 'suspended')),
  trial_ends_at     TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  archived_at       TIMESTAMPTZ
);

CREATE INDEX idx_partners_status ON partners(status) WHERE archived_at IS NULL;
```

### 2.2 `users`

```sql
CREATE TABLE users (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email             CITEXT NOT NULL UNIQUE,
  password_hash     TEXT NOT NULL,
  full_name         TEXT NOT NULL,
  user_type         TEXT NOT NULL
                    CHECK (user_type IN ('partner_user', 'customer_user', 'platform_admin')),
  partner_id        UUID REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID REFERENCES customers(id) ON DELETE CASCADE,
  role              TEXT NOT NULL DEFAULT 'member'
                    CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
  last_login_at     TIMESTAMPTZ,
  email_verified_at TIMESTAMPTZ,
  mfa_enabled       BOOLEAN NOT NULL DEFAULT false,
  mfa_secret        TEXT,
  status            TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'invited', 'suspended', 'deactivated')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT user_scope_valid CHECK (
    (user_type = 'partner_user' AND partner_id IS NOT NULL AND customer_id IS NULL)
    OR (user_type = 'customer_user' AND partner_id IS NOT NULL AND customer_id IS NOT NULL)
    OR (user_type = 'platform_admin' AND partner_id IS NULL AND customer_id IS NULL)
  )
);

CREATE INDEX idx_users_partner ON users(partner_id) WHERE status = 'active';
CREATE INDEX idx_users_customer ON users(customer_id) WHERE customer_id IS NOT NULL;
CREATE INDEX idx_users_email_lower ON users(lower(email));
```

### 2.3 `invitations`

```sql
CREATE TABLE invitations (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID REFERENCES customers(id) ON DELETE CASCADE,
  email             CITEXT NOT NULL,
  user_type         TEXT NOT NULL CHECK (user_type IN ('partner_user', 'customer_user')),
  role              TEXT NOT NULL DEFAULT 'member',
  token             TEXT NOT NULL UNIQUE,
  invited_by_user_id UUID NOT NULL REFERENCES users(id),
  expires_at        TIMESTAMPTZ NOT NULL,
  accepted_at       TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_invitations_token ON invitations(token) WHERE accepted_at IS NULL;
CREATE INDEX idx_invitations_partner ON invitations(partner_id);

ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
CREATE POLICY partner_access ON invitations FOR ALL
  USING (partner_id = current_setting('app.current_partner_id', true)::uuid)
  WITH CHECK (partner_id = current_setting('app.current_partner_id', true)::uuid);
```

### 2.4 `audit_log`

```sql
CREATE TABLE audit_log (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID REFERENCES partners(id) ON DELETE SET NULL,
  user_id           UUID REFERENCES users(id) ON DELETE SET NULL,
  action            TEXT NOT NULL,
  resource_type     TEXT NOT NULL,
  resource_id       UUID,
  payload           JSONB,
  ip_address        INET,
  user_agent        TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_partner_time ON audit_log(partner_id, created_at DESC);
CREATE INDEX idx_audit_resource ON audit_log(resource_type, resource_id);
-- Consider monthly partitioning for volume management
```

### 2.5 `industries` (platform-wide)

```sql
CREATE TABLE industries (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name              TEXT NOT NULL UNIQUE,
  slug              TEXT NOT NULL UNIQUE,
  sort_order        INTEGER NOT NULL DEFAULT 0,
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 2.6 `integration_categories` (platform-wide)

Generic capability categories. Partners connect integrations to fulfill these categories. The specific provider backing each connection is a detail the platform may expose or abstract.

```sql
CREATE TABLE integration_categories (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code              TEXT NOT NULL UNIQUE,           -- 'website', 'analytics', 'keywords', 'ads', 'social', 'email', 'call_tracking', 'heatmap'
  name              TEXT NOT NULL,                  -- Display name
  description       TEXT,
  required_fields   JSONB NOT NULL DEFAULT '[]',    -- [{name, label, type, secret: bool}]
  supports_webhook  BOOLEAN NOT NULL DEFAULT false,
  is_active         BOOLEAN NOT NULL DEFAULT true,
  sort_order        INTEGER NOT NULL DEFAULT 0,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Seed categories for v1:** `website`, `analytics`, `keywords`, `ads`, `social`, `email`, `call_tracking`, `heatmap`. Each category has its own `required_fields` schema defining what credentials/configuration Partners provide when connecting.

---

## 3. Billing Layer (Tables 7–14)

The billing layer abstracts the underlying billing provider. Provider-specific identifiers are stored as opaque strings — the schema does not assume any particular backend.

### 3.1 `subscription_plans`

```sql
CREATE TABLE subscription_plans (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code              TEXT NOT NULL UNIQUE,
  name              TEXT NOT NULL,
  description       TEXT,
  provider_price_id_base        TEXT NOT NULL,     -- External price ID for base per-Partner charge
  provider_price_id_per_customer TEXT NOT NULL,    -- External price ID for per-Customer charge
  base_price_cents  INTEGER NOT NULL,
  per_customer_price_cents INTEGER NOT NULL,
  included_customers INTEGER NOT NULL DEFAULT 0,
  included_ai_tokens BIGINT NOT NULL DEFAULT 0,
  max_customers     INTEGER,
  max_partner_users INTEGER,
  features          JSONB NOT NULL DEFAULT '{}',
  is_active         BOOLEAN NOT NULL DEFAULT true,
  sort_order        INTEGER NOT NULL DEFAULT 0,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.2 `subscription_addons`

Token tier upgrades, stackable and additive.

```sql
CREATE TABLE subscription_addons (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code              TEXT NOT NULL UNIQUE,
  name              TEXT NOT NULL,
  description       TEXT,
  provider_price_id TEXT NOT NULL,
  addon_type        TEXT NOT NULL DEFAULT 'token_tier'
                    CHECK (addon_type IN ('token_tier')),
  included_ai_tokens BIGINT NOT NULL,
  price_cents       INTEGER NOT NULL,
  is_active         BOOLEAN NOT NULL DEFAULT true,
  sort_order        INTEGER NOT NULL DEFAULT 0,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.3 `partner_billing_accounts`

Maps Partners to their external billing provider account. The provider is tracked by code to allow multi-provider futures.

```sql
CREATE TABLE partner_billing_accounts (
  partner_id            UUID PRIMARY KEY REFERENCES partners(id) ON DELETE CASCADE,
  billing_provider      TEXT NOT NULL DEFAULT 'default',  -- Provider identifier (opaque to app logic)
  provider_customer_id  TEXT NOT NULL UNIQUE,              -- External billing-system customer ID
  default_payment_method_id TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.4 `partner_subscriptions`

```sql
CREATE TABLE partner_subscriptions (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id                UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  plan_id                   UUID NOT NULL REFERENCES subscription_plans(id),
  provider_subscription_id  TEXT NOT NULL UNIQUE,
  status                    TEXT NOT NULL
                            CHECK (status IN ('trialing', 'active', 'past_due', 'canceled', 'unpaid', 'incomplete')),
  current_period_start      TIMESTAMPTZ NOT NULL,
  current_period_end        TIMESTAMPTZ NOT NULL,
  cancel_at_period_end      BOOLEAN NOT NULL DEFAULT false,
  canceled_at               TIMESTAMPTZ,
  trial_end                 TIMESTAMPTZ,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_partner_sub_active ON partner_subscriptions(partner_id)
  WHERE status IN ('trialing', 'active', 'past_due');
```

### 3.5 `partner_subscription_items`

```sql
CREATE TABLE partner_subscription_items (
  id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subscription_id               UUID NOT NULL REFERENCES partner_subscriptions(id) ON DELETE CASCADE,
  provider_subscription_item_id TEXT NOT NULL UNIQUE,
  item_type                     TEXT NOT NULL
                                CHECK (item_type IN ('base', 'per_customer', 'addon')),
  addon_id                      UUID REFERENCES subscription_addons(id),
  quantity                      INTEGER NOT NULL DEFAULT 1,
  created_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT addon_has_addon_id CHECK (
    (item_type = 'addon' AND addon_id IS NOT NULL)
    OR (item_type != 'addon' AND addon_id IS NULL)
  )
);

CREATE INDEX idx_sub_items_sub ON partner_subscription_items(subscription_id);
```

**Key rules:**
- `item_type = 'per_customer'` quantity equals count of active, non-archived Customers. Maintained via domain events on `customers` status changes.
- `item_type = 'addon'` items are active token tier upgrades. Multiple of the same tier can stack.

### 3.6 `ai_token_usage`

Every AI generation call is logged here, scoped to the Partner (and optionally Customer) that triggered it.

```sql
CREATE TABLE ai_token_usage (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID REFERENCES customers(id) ON DELETE SET NULL,
  user_id           UUID REFERENCES users(id) ON DELETE SET NULL,

  -- Provider (opaque to app logic; for reconciliation and analytics)
  ai_provider       TEXT NOT NULL DEFAULT 'default',
  model             TEXT NOT NULL,
  provider_request_id TEXT,                        -- External request ID for reconciliation

  -- Token accounting
  input_tokens      INTEGER NOT NULL DEFAULT 0,
  output_tokens     INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_write_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens      INTEGER GENERATED ALWAYS AS
                      (input_tokens + output_tokens + cache_read_tokens + cache_write_tokens) STORED,

  -- Cost tracking (estimated at call time; authoritative bill comes from provider)
  estimated_cost_cents INTEGER,

  -- App context
  feature           TEXT NOT NULL,                 -- 'blog_generation', 'seo_page_fields', 'keyword_scoring', etc.

  billable_period   DATE NOT NULL,                 -- First of month — for fast aggregation
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_token_usage_partner_period ON ai_token_usage(partner_id, billable_period);
CREATE INDEX idx_token_usage_customer ON ai_token_usage(customer_id, created_at DESC);
CREATE INDEX idx_token_usage_feature ON ai_token_usage(feature, created_at DESC);

ALTER TABLE ai_token_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY partner_access ON ai_token_usage FOR ALL
  USING (partner_id = current_setting('app.current_partner_id', true)::uuid);
```

### 3.7 `partner_token_balance`

Fast materialized aggregate for cap enforcement.

```sql
CREATE TABLE partner_token_balance (
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  billable_period   DATE NOT NULL,
  included_tokens   BIGINT NOT NULL DEFAULT 0,
  tokens_used       BIGINT NOT NULL DEFAULT 0,
  tokens_remaining  BIGINT GENERATED ALWAYS AS (included_tokens - tokens_used) STORED,
  cap_warned_at     TIMESTAMPTZ,
  cap_reached_at    TIMESTAMPTZ,
  last_updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  PRIMARY KEY (partner_id, billable_period)
);

CREATE INDEX idx_token_balance_throttled ON partner_token_balance(partner_id, billable_period)
  WHERE cap_reached_at IS NOT NULL;
```

**Update flow:**

1. AI call requested → check `tokens_remaining`
2. Block if `<= 0`
3. On success → insert `ai_token_usage` row, update `partner_token_balance.tokens_used`
4. Cross 80% threshold → set `cap_warned_at`, emit warning event
5. Cross 100% → set `cap_reached_at`, emit throttle event

Updates via domain event pattern, not DB triggers.

### 3.8 `billing_webhook_events`

Inbound webhook events from the billing provider. Provider-agnostic schema.

```sql
CREATE TABLE billing_webhook_events (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  billing_provider  TEXT NOT NULL DEFAULT 'default',
  provider_event_id TEXT NOT NULL,                 -- External event ID for idempotency
  event_type        TEXT NOT NULL,
  payload           JSONB NOT NULL,
  processed_at      TIMESTAMPTZ,
  processing_error  TEXT,
  received_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (billing_provider, provider_event_id)
);

CREATE INDEX idx_billing_webhook_unprocessed ON billing_webhook_events(received_at)
  WHERE processed_at IS NULL;
```

---

## 4. Customer Core (Tables 15–17)

### 4.1 `customers`

```sql
CREATE TABLE customers (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  slug              TEXT NOT NULL,
  primary_email     CITEXT,
  website_url       TEXT,
  industry_id       UUID REFERENCES industries(id),
  currency          TEXT NOT NULL DEFAULT 'USD' CHECK (currency IN ('USD', 'CAD', 'EUR', 'GBP', 'AUD')),
  customer_type     TEXT CHECK (customer_type IN ('lead_gen', 'ecommerce', 'hybrid', 'other')),
  timezone          TEXT NOT NULL DEFAULT 'UTC',
  status            TEXT NOT NULL DEFAULT 'prep'
                    CHECK (status IN ('prep', 'active', 'on_hold', 'archived')),
  notes             TEXT,
  legacy_source_id  TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  archived_at       TIMESTAMPTZ,

  UNIQUE (partner_id, slug)
);

CREATE INDEX idx_customers_partner_status ON customers(partner_id, status)
  WHERE archived_at IS NULL;

ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
CREATE POLICY partner_access ON customers FOR ALL
  USING (partner_id = current_setting('app.current_partner_id', true)::uuid)
  WITH CHECK (partner_id = current_setting('app.current_partner_id', true)::uuid);
CREATE POLICY customer_read_own ON customers FOR SELECT
  USING (
    id = current_setting('app.current_customer_id', true)::uuid
    AND partner_id = current_setting('app.current_partner_id', true)::uuid
  );
```

### 4.2 `customer_services`

```sql
CREATE TABLE customer_services (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL UNIQUE REFERENCES customers(id) ON DELETE CASCADE,
  seo_notes         TEXT,
  ads_notes         TEXT,
  social_notes      TEXT,
  email_notes       TEXT,
  website_notes     TEXT,
  creative_notes    TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Active service areas (previously multi-select fields)
CREATE TABLE customer_service_channels (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  service_area      TEXT NOT NULL CHECK (service_area IN
                      ('seo', 'ads', 'social', 'email', 'website', 'creative', 'reporting', 'analytics')),
  channel_label     TEXT NOT NULL,                  -- Partner-defined label (e.g., "Search Ads", "Company Page")
  is_active         BOOLEAN NOT NULL DEFAULT true,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (customer_id, service_area, channel_label)
);

ALTER TABLE customer_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_service_channels ENABLE ROW LEVEL SECURITY;
-- Apply standard partner_access + customer_read policies
```

**Key change:** `channel_label` is Partner-defined text rather than a platform-controlled enum. Partners can organize their service delivery however they prefer without being constrained to the categories a specific vendor uses.

### 4.3 `customer_documents`

```sql
CREATE TABLE customer_documents (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  document_type     TEXT NOT NULL CHECK (document_type IN
                      ('project_doc', 'audit_context', 'audit_summary', 'report', 'other')),
  name              TEXT NOT NULL,
  version           TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'current'
                    CHECK (status IN ('current', 'stale', 'archived')),
  content           TEXT,
  content_format    TEXT NOT NULL DEFAULT 'markdown'
                    CHECK (content_format IN ('markdown', 'html', 'plaintext', 'json')),
  metadata          JSONB,
  created_by_user_id UUID REFERENCES users(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_customer_docs_type ON customer_documents(customer_id, document_type, status);

ALTER TABLE customer_documents ENABLE ROW LEVEL SECURITY;
```

---

## 5. Brand Layer (Tables 18–23)

### 5.1 `brand_voice`

```sql
CREATE TABLE brand_voice (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL UNIQUE REFERENCES customers(id) ON DELETE CASCADE,
  tone_descriptors  TEXT[],
  voice_detail      TEXT,
  dos               TEXT[],
  donts             TEXT[],
  example_phrases   TEXT[],
  legacy_source_id  TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.2 `brand_voice_inputs`

```sql
CREATE TABLE brand_voice_inputs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  input_type        TEXT,
  content           TEXT NOT NULL,
  submitted_by      TEXT,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.3 `target_audiences`

```sql
CREATE TABLE target_audiences (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  rank              INTEGER NOT NULL DEFAULT 99,
  demographics      JSONB,
  psychographics    JSONB,
  buyer_stage       TEXT CHECK (buyer_stage IN ('awareness', 'consideration', 'decision', 'retention')),
  description       TEXT,
  pain_points       TEXT[],
  goals             TEXT[],
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audiences_rank ON target_audiences(customer_id, rank);
```

### 5.4 `info_base_entries`

```sql
CREATE TABLE info_base_entries (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  category          TEXT,
  title             TEXT NOT NULL,
  content           TEXT NOT NULL,
  is_key_message    BOOLEAN NOT NULL DEFAULT false,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_info_base_customer ON info_base_entries(customer_id, category);
```

### 5.5 `products_and_services`

```sql
CREATE TABLE products_and_services (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  type              TEXT NOT NULL CHECK (type IN ('product', 'service', 'bundle')),
  description       TEXT,
  price_cents       INTEGER,
  currency          TEXT,
  price_model       TEXT,
  url               TEXT,
  is_featured       BOOLEAN NOT NULL DEFAULT false,
  sort_order        INTEGER NOT NULL DEFAULT 0,
  metadata          JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.6 `customer_contacts`

```sql
CREATE TABLE customer_contacts (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  full_name         TEXT NOT NULL,
  title             TEXT,
  email             CITEXT,
  phone             TEXT,
  is_primary        BOOLEAN NOT NULL DEFAULT false,
  receives_reports  BOOLEAN NOT NULL DEFAULT false,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_contacts_primary ON customer_contacts(customer_id)
  WHERE is_primary = true;
```

---

## 6. Strategy Layer (Tables 24–33)

### 6.1 `content_strategies`

```sql
CREATE TABLE content_strategies (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL UNIQUE REFERENCES customers(id) ON DELETE CASCADE,
  version           TEXT,
  strategy          JSONB NOT NULL,
  last_reviewed_at  TIMESTAMPTZ,
  status            TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('draft', 'active', 'archived')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 6.2 `keyword_target_list`

The list of keywords a Customer is targeting. Canonical target source for content planning.

```sql
CREATE TABLE keyword_target_list (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  keyword           TEXT NOT NULL,
  tags              TEXT[],

  -- Universal SEO metrics (provider-neutral)
  search_volume     INTEGER,
  keyword_difficulty INTEGER CHECK (keyword_difficulty BETWEEN 0 AND 100),
  search_intent     TEXT CHECK (search_intent IN ('informational', 'navigational', 'commercial', 'transactional')),
  competition       DECIMAL(3,2),
  cpc_cents         INTEGER,
  serp_features     TEXT[],

  -- Three-dimension scoring
  volume_score      DECIMAL(5,2),
  audience_relevance_score DECIMAL(5,2),
  competitive_score DECIMAL(5,2),
  opportunity_score DECIMAL(5,2),

  source            TEXT,                           -- 'keyword_tool', 'manual', 'import' (generic)
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (customer_id, keyword)
);

CREATE INDEX idx_target_opportunity ON keyword_target_list(customer_id, opportunity_score DESC NULLS LAST);
CREATE INDEX idx_target_tags ON keyword_target_list USING GIN(tags);
```

### 6.3 `keyword_rankings`

Time-series snapshots of ranking positions.

```sql
CREATE TABLE keyword_rankings (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  target_keyword_id UUID REFERENCES keyword_target_list(id) ON DELETE SET NULL,
  keyword           TEXT NOT NULL,
  position          INTEGER,
  landing_page      TEXT,
  search_volume     INTEGER,
  trend_data        JSONB,                          -- Historical position data from keyword integration
  snapshot_date     DATE NOT NULL,
  imported_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rankings_customer_date ON keyword_rankings(customer_id, snapshot_date DESC);
CREATE INDEX idx_rankings_keyword_date ON keyword_rankings(customer_id, keyword, snapshot_date DESC);
```

### 6.4 `keyword_research`

```sql
CREATE TABLE keyword_research (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  research_name     TEXT NOT NULL,
  seed_keywords     TEXT[],
  notes             TEXT,
  raw_data          JSONB,
  status            TEXT NOT NULL DEFAULT 'active',
  created_by_user_id UUID REFERENCES users(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 6.5 `keyword_groups` and `keyword_group_members`

```sql
CREATE TABLE keyword_groups (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  description       TEXT,
  parent_group_id   UUID REFERENCES keyword_groups(id) ON DELETE CASCADE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (customer_id, name)
);

CREATE TABLE keyword_group_members (
  group_id          UUID NOT NULL REFERENCES keyword_groups(id) ON DELETE CASCADE,
  target_keyword_id UUID NOT NULL REFERENCES keyword_target_list(id) ON DELETE CASCADE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (group_id, target_keyword_id)
);
```

### 6.6 `taxonomies`

```sql
CREATE TABLE taxonomies (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id         UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id        UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  taxonomy_type      TEXT NOT NULL CHECK (taxonomy_type IN ('category', 'tag', 'post_type', 'custom')),
  name               TEXT NOT NULL,
  slug               TEXT NOT NULL,
  parent_id          UUID REFERENCES taxonomies(id) ON DELETE CASCADE,
  description        TEXT,
  external_ref_id    TEXT,                          -- Generic external reference (e.g., Website CMS term ID)
  sort_order         INTEGER NOT NULL DEFAULT 0,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (customer_id, taxonomy_type, slug)
);
```

### 6.7 `ai_content_instructions`

```sql
CREATE TABLE ai_content_instructions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  content_type      TEXT NOT NULL CHECK (content_type IN
                      ('blog_post', 'seo_page_fields', 'seo_page_html', 'email_campaign',
                       'social_post', 'short_video', 'custom_post', 'ad_copy')),
  seo_page_field_template_id UUID REFERENCES seo_page_field_templates(id),
  seo_page_html_template_id  UUID REFERENCES seo_page_html_templates(id),
  instructions      TEXT NOT NULL,
  set_status_to     TEXT DEFAULT 'planning' CHECK (set_status_to IN ('planning', 'scheduled', 'draft')),
  create_per_run    INTEGER DEFAULT 1,
  run_frequency     TEXT CHECK (run_frequency IN ('manual', 'weekly', 'monthly')),
  last_run_at       TIMESTAMPTZ,
  next_run_at       TIMESTAMPTZ,
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Note:** `short_video` replaces the previous `youtube_short` — content type is format-specific, not platform-specific.

### 6.8 `ai_general_instructions`

```sql
CREATE TABLE ai_general_instructions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID NOT NULL UNIQUE REFERENCES customers(id) ON DELETE CASCADE,
  global_instructions TEXT,
  banned_phrases    TEXT[],
  required_phrases  TEXT[],
  preferred_style   JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 6.9 `seo_page_field_templates` and `seo_page_html_templates`

```sql
CREATE TABLE seo_page_field_templates (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID REFERENCES customers(id) ON DELETE CASCADE, -- NULL = partner-wide
  name              TEXT NOT NULL,
  description       TEXT,
  field_schema      JSONB NOT NULL,
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE seo_page_html_templates (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id       UUID REFERENCES customers(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  description       TEXT,
  html_template     TEXT NOT NULL,
  field_template_id UUID REFERENCES seo_page_field_templates(id),
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 7. Integrations Layer (Tables 34–36)

### 7.1 `customer_integrations`

Partners connect integrations by selecting a category and providing credentials. The platform does not expose which specific vendors back each category in the schema.

```sql
CREATE TABLE customer_integrations (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id             UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  customer_id            UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  integration_category_id UUID NOT NULL REFERENCES integration_categories(id),
  name                   TEXT,                      -- Partner-defined label
  credentials_encrypted  BYTEA,                     -- pgcrypto-encrypted JSON
  config                 JSONB,                     -- Non-sensitive config
  status                 TEXT NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'active', 'error', 'disconnected')),
  last_sync_at           TIMESTAMPTZ,
  last_error             TEXT,
  connected_by_user_id   UUID REFERENCES users(id),
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (customer_id, integration_category_id, name)
);

CREATE INDEX idx_integrations_status ON customer_integrations(status)
  WHERE status = 'active';
```

**Key change:** `UNIQUE (customer_id, integration_category_id, name)` allows a Customer to have multiple integrations in the same category — e.g., two Analytics integrations backed by different providers. The `name` field disambiguates.

**Security:** `credentials_encrypted` uses `pgcrypto` with a key managed via external KMS (AWS KMS, Vault, etc.). Credentials never appear in logs or responses.

### 7.2 `integration_sync_log`

```sql
CREATE TABLE integration_sync_log (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  integration_id    UUID NOT NULL REFERENCES customer_integrations(id) ON DELETE CASCADE,
  sync_type         TEXT NOT NULL,                  -- 'scheduled', 'manual', 'webhook'
  status            TEXT NOT NULL CHECK (status IN ('success', 'partial', 'failed')),
  records_fetched   INTEGER,
  records_written   INTEGER,
  error_details     JSONB,
  started_at        TIMESTAMPTZ NOT NULL,
  completed_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sync_log_integration ON integration_sync_log(integration_id, started_at DESC);
```

### 7.3 `integration_webhooks`

```sql
CREATE TABLE integration_webhooks (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  integration_id    UUID NOT NULL REFERENCES customer_integrations(id) ON DELETE CASCADE,
  webhook_secret    TEXT NOT NULL,
  webhook_url_path  TEXT NOT NULL UNIQUE,
  events_subscribed TEXT[],
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 8. Cross-Cutting Infrastructure

### 8.1 Shared `updated_at` trigger

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### 8.2 Customer count → subscription quantity

Domain event pattern (not DB triggers — external API calls from triggers are problematic):

```python
async def update_customer_status(customer_id: UUID, new_status: str):
    async with db.transaction():
        old_status = await get_status(customer_id)
        await set_status(customer_id, new_status)

        if was_billable(old_status) != is_billable(new_status):
            await emit_event("customer.billing_status_changed", {
                "partner_id": partner_id,
                "customer_id": customer_id,
            })
# Event handler runs async, calls billing provider, updates partner_subscription_items
```

`is_billable(status)` = `status IN ('prep', 'active', 'on_hold')`. Archived = not billed.

### 8.3 Token cap enforcement flow

```
User triggers AI feature → app calls internal AI gateway → gateway checks partner_token_balance
  ├─ Remaining > 0 and not at cap:
  │   ├─ Make AI provider API call
  │   ├─ Extract actual token counts from provider response
  │   ├─ INSERT into ai_token_usage (billable_period = current month)
  │   ├─ Emit: token_usage.recorded
  │   └─ Async worker: UPDATE partner_token_balance.tokens_used
  │       ├─ Cross 80% → SET cap_warned_at, emit token_usage.warning_threshold
  │       └─ Cross 100% → SET cap_reached_at, emit token_usage.cap_reached
  │
  └─ At or over cap:
      └─ Return 429 with upgrade URL and available token tier
```

**Month rollover:** Cron job on the 1st of each month creates fresh `partner_token_balance` rows, seeding `included_tokens` from current plan + active addons.

**Addon purchase mid-period:** Immediately update current period's `included_tokens`, clear `cap_reached_at`.

### 8.4 AI gateway architecture

All AI provider API calls route through a single internal gateway service:

```
App feature
  ↓
Internal AI gateway
  ├─ Cap check (read partner_token_balance)
  ├─ Rate limit check
  ├─ Model routing (based on feature)
  ├─ AI provider API call
  ├─ Extract token counts from response
  ├─ Write ai_token_usage row
  └─ Return response to app feature
```

The gateway is the only code path that talks to any AI provider. No direct provider calls from feature code. Enforce via code review and network policy (only gateway has outbound access to provider endpoints).

This isolation allows:
- Swapping or adding AI providers without touching feature code
- Accurate token accounting (no way to bypass)
- Centralized rate limiting and retry logic
- Provider-agnostic prompt routing

### 8.5 Extensions required

```sql
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

---

## 9. Table Count Summary

| Layer | Tables | Notes |
|---|---|---|
| Platform | 6 | partners, users, invitations, audit_log, industries, integration_categories |
| Billing | 8 | plans, addons, partner_billing_accounts, subscriptions, items, token_usage, token_balance, webhook_events |
| Customer Core | 3 | customers, services (+ channels join table), documents |
| Brand | 6 | voice, voice_inputs, audiences, info_base, products, contacts |
| Strategy | 10 | strategies, 2 keyword lists, research, 2 group tables, taxonomies, 2 AI instructions, 2 templates |
| Integrations | 3 | integrations, sync_log, webhooks |
| **Total v3** | **36 core + join tables** | |
| **Still v4** | ~20 | Content (7), Analytics (5), Work Mgmt (4), Audit (2), misc |

**v1 total projection: ~56 tables**

---

## 10. Vendor Neutrality Checklist

Before any schema or UI ships, confirm:

- [ ] No table or column name references a specific vendor product
- [ ] No enum value references a specific vendor product
- [ ] No comment in DDL references a specific vendor (clean internal comments are fine)
- [ ] `integration_categories` seed data uses generic codes only
- [ ] Billing provider identifiers are opaque strings, not typed references
- [ ] AI provider identifiers are opaque strings, not typed references
- [ ] External reference IDs on records (like `taxonomies.external_ref_id`) are generic — no `wordpress_term_id` or equivalents
- [ ] Partner-facing UI never shows vendor names unless the Partner explicitly chose/configured them
- [ ] API responses never leak vendor names in field names or enums
- [ ] Error messages reference generic categories, not vendors (e.g., "Website integration failed" not "WordPress integration failed")

---

## 11. Open Items Before v4

1. **Content status pipeline** — what are the valid states for `blog_posts.status`, `seo_pages.status`, etc.? (Proposed: `idea → planning → draft → scheduled → published → archived`)
2. **Publishing model** — is "publish to Website integration" a content status transition, an action on an integration, or a separate `content_publications` table tracking history? Affects content layer schema.
3. **Partner-wide templates** — `seo_page_*_templates` have nullable `customer_id` for Partner-wide reuse. Should `ai_content_instructions` also support Partner-wide versions?
4. **Analytics snapshot retention** — indefinite, or time-capped per plan tier?
5. **File/attachment strategy** — object storage (S3-compatible) + `files` table for uploads (logos, images, exports)?
6. **Seed data** — industries list (~40 entries), integration_categories catalog (8 generic categories).

---

## 12. Next Step

v4: Content, Campaigns, Analytics, Reporting, Work Management, Audit layers DDL (~20 tables).

Recommend resolving open items #1 (content status pipeline) and #2 (publishing model) before v4 — those shape the content layer architecturally.
