# Database Schema

Marketing management SaaS. Partners are agencies that purchase the platform; Customers are client accounts belonging to a Partner. Users belong to either a Partner or a Customer — or neither (admin-tier users). All timestamps stored in UTC as `TIMESTAMPTZ`.

**Database:** PostgreSQL (Railway)  
**Extensions:** `citext`, `pgcrypto`, `pg_trgm`  
**Triggers:** `set_updated_at()` fires `BEFORE UPDATE` on `partners`, `customers`, `users`, `plans`, `blog_posts`, `brand_voice`, `customer_contacts`, `customer_documents`, `customer_services`, `info_base_entries`, `products_and_services`, `target_audiences`, `chat_sessions`  
**Row Level Security:** Enabled on all tenant tables. Core tables (`partners`, `customers`, `users`, `ai_token_usage`, `partner_token_balance`, `chat_sessions`, `chat_messages`, `chat_session_shares`) use `FORCE`. The customer-profile tables (`customer_services`, `customer_service_channels`, `customer_documents`, `brand_voice`, `brand_voice_inputs`, `target_audiences`, `info_base_entries`, `products_and_services`, `customer_contacts`) have RLS enabled without `FORCE`. `blog_posts` and `blog_post_versions` do not yet have RLS enabled. Policies use four session variables: `app.bypass_rls`, `app.current_partner_id`, `app.current_customer_id`, `app.current_user_id`. Application connects as `app_user` (non-superuser) so RLS fires. Admin sets `bypass_rls = 'true'`; partner users set partner/user IDs only; customer users set all four.  
**Application DB role:** `app_user` — used by FastAPI for all queries. `postgres` used for migrations/admin only.

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

**Constraints:** `plans_name_key` — `name` unique  

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

**Constraints:** `industries_name_key` — `name` unique; `industries_slug_key` — `slug` unique  

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

**Constraints:** `partners_slug_key` — `slug` unique; `partners_status_check` — status IN (trial, active, past_due, canceled, suspended)  
**Indexes:** `idx_partners_status` on `status` WHERE `archived_at IS NULL`

---

### `customers`
Client accounts owned by a Partner.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `name` | `varchar(255)` | NO | | |
| `slug` | `text` | NO | | Auto-generated from name; globally unique |
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

**Constraints:** `uq_customers_slug` — `slug` unique (global); `customers_currency_check` — currency IN (USD, CAD, EUR, GBP, AUD); `customers_customer_type_check` — customer_type IN (lead_gen, ecommerce, hybrid, other); `customers_status_check` — status IN (prep, active, on_hold, archived)  
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
| `tier` | `varchar(20)` | NO | | `admin`, `partner`, or `customer` |
| `display_name` | `varchar(100)` | YES | | Human-readable label for UI |
| `description` | `text` | YES | | |
| `is_default` | `boolean` | NO | `false` | Default role assigned for that tier on signup |
| `sort_order` | `integer` | NO | `99` | Display order |
| `created_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `roles_name_key` — `name` unique; `roles_tier_check` — tier IN (admin, partner, customer)

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

**Constraints:** `permissions_key_key` — `key` unique  

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

### `app_agents`
Registry of available AI agents in the platform. Global agents (`partner_id IS NULL`) are available to all partners; partner-scoped agents override or extend the global set for a specific partner.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `key` | `text` | NO | | PK. Stable identifier e.g. `general_assistant` |
| `console_agent_id` | `text` | NO | `''` | Agent ID from the Anthropic Console |
| `label` | `text` | NO | | Display name shown in the UI |
| `category` | `text` | NO | | Grouping label e.g. `marketing`, `support` |
| `description` | `text` | NO | | Short description shown to users |
| `is_default` | `boolean` | NO | `false` | Whether this agent is pre-selected for new sessions |
| `enabled` | `boolean` | NO | `true` | Soft-disable without deleting |
| `partner_id` | `integer` | YES | | FK → `partners.id` ON DELETE CASCADE — NULL = global agent |
| `thinking_default` | `boolean` | NO | `false` | Whether extended thinking is enabled by default for this agent |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Indexes:**
- `idx_app_agents_category` on `category` WHERE `enabled = true`
- `idx_app_agents_partner` on `partner_id` WHERE `enabled = true AND partner_id IS NOT NULL`

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

### `chat_sessions`
Conversational AI sessions owned by a user. Distinct from AI generation tasks — only interactive chats are stored here.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE — tenant scope |
| `user_id` | `integer` | NO | | FK → `users.id` ON DELETE CASCADE — owner |
| `customer_id` | `integer` | YES | | FK → `customers.id` ON DELETE SET NULL — optional client context |
| `title` | `text` | YES | | User-editable or auto-generated from first message |
| `current_agent_key` | `text` | YES | | FK → `app_agents.key` ON DELETE SET NULL — active agent for this session |
| `archived_at` | `timestamptz` | YES | | Soft delete |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Indexes:** `idx_chat_sessions_user` on `(user_id, updated_at DESC)`, `idx_chat_sessions_partner` on `partner_id`, `idx_chat_sessions_customer` on `customer_id` WHERE `customer_id IS NOT NULL`

---

### `chat_messages`
Individual turns within a chat session. Role matches the Anthropic/OpenAI message format.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `bigserial` | NO | auto-increment | PK |
| `session_id` | `integer` | NO | | FK → `chat_sessions.id` ON DELETE CASCADE |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE — denormalized for access control |
| `role` | `text` | NO | | `user`, `assistant`, or `system` |
| `content` | `text` | NO | | Message body |
| `model` | `text` | YES | | AI model used; null for user/system turns |
| `created_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `chat_messages_role_check` — role IN (user, assistant, system)  
**Indexes:** `idx_chat_messages_session` on `(session_id, created_at ASC)`

---

### `chat_session_shares`
Grants specific partner-account users read access to a session they don't own.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `session_id` | `integer` | NO | | PK, FK → `chat_sessions.id` ON DELETE CASCADE |
| `shared_with_user_id` | `integer` | NO | | PK, FK → `users.id` ON DELETE CASCADE |
| `shared_by_user_id` | `integer` | YES | | FK → `users.id` ON DELETE SET NULL — who granted access |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE — denormalized for RLS and query performance |
| `created_at` | `timestamptz` | NO | `now()` | |

**Indexes:** `idx_chat_session_shares_user` on `shared_with_user_id`, `idx_chat_session_shares_partner` on `partner_id`

---

### `blog_posts`
Blog posts created for a customer. Supports a full editorial workflow from draft through to published. Body content is stored as markdown, optional rich-text JSON (e.g. TipTap/ProseMirror), and rendered HTML.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE |
| `created_by_user_id` | `integer` | NO | | FK → `users.id` ON DELETE NO ACTION |
| `title` | `text` | NO | | Post title |
| `slug` | `text` | NO | | URL-friendly identifier; unique per customer |
| `excerpt` | `text` | YES | | Short summary / meta preview |
| `status` | `text` | NO | `'draft'` | `draft`, `review`, `scheduled`, `published`, `archived` |
| `reviewer_user_id` | `integer` | YES | | FK → `users.id` ON DELETE NO ACTION — assigned reviewer |
| `review_requested_at` | `timestamptz` | YES | | When review was requested |
| `review_notes` | `text` | YES | | Reviewer feedback |
| `scheduled_for` | `timestamptz` | YES | | Publish time when status = `scheduled` |
| `published_at` | `timestamptz` | YES | | Timestamp when post was published |
| `published_by_user_id` | `integer` | YES | | FK → `users.id` ON DELETE NO ACTION |
| `archived_at` | `timestamptz` | YES | | Soft delete timestamp |
| `body_markdown` | `text` | NO | `''` | Canonical markdown body |
| `body_json` | `jsonb` | YES | | Rich-text editor AST (e.g. TipTap) |
| `body_html` | `text` | YES | | Rendered HTML for display |
| `word_count` | `integer` | NO | `0` | Computed word count |
| `reading_time_sec` | `integer` | NO | `0` | Estimated reading time in seconds |
| `meta_description` | `text` | YES | | SEO meta description |
| `focus_keyword` | `text` | YES | | Primary SEO keyword |
| `og_title` | `text` | YES | | Open Graph title override |
| `og_image_url` | `text` | YES | | Open Graph image URL |
| `canonical_url` | `text` | YES | | Canonical URL override |
| `meta_robots` | `text` | NO | `'index,follow'` | Robots meta directive |
| `featured_image_url` | `text` | YES | | Hero/featured image URL |
| `template_key` | `text` | YES | | FK → `blog_templates.key` — layout template identifier |
| `generated_by_agent_key` | `text` | YES | | Agent key that generated this post (informational) |
| `topic` | `text` | YES | | High-level topic or category label |
| `target_audience_id` | `integer` | YES | | FK → `target_audiences.id` ON DELETE SET NULL |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `blog_posts_status_check` — status IN (draft, review, scheduled, published, archived)  
**Unique indexes:** `blog_posts_slug_unique_per_customer` — `(customer_id, slug)`  
**Indexes:**
- `ix_blog_posts_partner_customer_status_updated` on `(partner_id, customer_id, status, updated_at DESC)`
- `ix_blog_posts_published_at` on `(customer_id, published_at DESC)` WHERE `status = 'published'`
- `ix_blog_posts_scheduled_for` on `scheduled_for` WHERE `status = 'scheduled'`

**RLS:** Not yet enabled on this table.

---

### `blog_post_versions`
Immutable version history for blog posts. A new row is appended whenever the post body is saved (manually, via autosave, via AI generation, or on a status transition).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `post_id` | `integer` | NO | | FK → `blog_posts.id` ON DELETE CASCADE |
| `partner_id` | `integer` | NO | | Denormalized partner scope (no FK constraint) |
| `body_markdown` | `text` | NO | | Full markdown body snapshot |
| `body_json` | `jsonb` | YES | | Rich-text AST snapshot |
| `word_count` | `integer` | NO | `0` | Word count at time of save |
| `created_at` | `timestamptz` | NO | `now()` | |
| `created_by_user_id` | `integer` | YES | | FK → `users.id` ON DELETE NO ACTION |
| `source` | `text` | NO | | How the version was created: `manual_save`, `autosave`, `ai:blog_writer`, `ai:revise`, `status_change` |
| `note` | `text` | YES | | Optional human note describing the version |

**Constraints:** `blog_post_versions_source_check` — source IN (manual_save, autosave, ai:blog_writer, ai:revise, status_change)  
**Indexes:** `ix_blog_post_versions_post_created` on `(post_id, created_at DESC)`

**RLS:** Not yet enabled on this table.

---

### `blog_templates`
Reusable content templates that define structure and AI prompting guidance for blog post generation. Global registry — not scoped per partner or customer. Referenced by `blog_posts.template_key`.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `key` | `text` | NO | | PK. Stable identifier e.g. `how_to_guide` |
| `surface` | `text` | NO | `'blog'` | Content surface this template targets e.g. `blog` |
| `label` | `text` | NO | | Display name shown in the UI |
| `description` | `text` | NO | | Short description of the template's purpose |
| `icon` | `text` | NO | | Icon identifier for UI display |
| `scaffold_markdown` | `text` | NO | `''` | Starter markdown structure placed into the editor |
| `structure_prompt` | `text` | NO | `''` | AI system prompt guidance for content structure |
| `suggested_word_count_min` | `integer` | NO | `200` | Lower bound of suggested word count range |
| `suggested_word_count_max` | `integer` | NO | `1500` | Upper bound of suggested word count range |
| `sort_order` | `integer` | NO | `0` | Display order within a surface |
| `is_active` | `boolean` | NO | `true` | Soft-disable without deleting |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Indexes:** `ix_blog_templates_surface_active` on `(surface, sort_order)` WHERE `is_active = true`

---

### `customer_services`
One-row-per-customer record storing agency service scope and high-level notes for each marketing channel delivered to a customer. At most one row per customer (unique on `customer_id`).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE — unique |
| `seo_notes` | `text` | YES | | |
| `ads_notes` | `text` | YES | | |
| `social_notes` | `text` | YES | | |
| `email_notes` | `text` | YES | | |
| `website_notes` | `text` | YES | | |
| `creative_notes` | `text` | YES | | |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `customer_services_customer_id_key` — `customer_id` unique  
**Indexes:** `idx_customer_services_partner` on `partner_id`  
**RLS policies:** `partner_access` — ALL where `partner_id = app.current_partner_id`

---

### `customer_service_channels`
Individual delivery channels per service area for a customer. Multiple channels can exist per `(customer_id, service_area)` — e.g. separate Google Ads and Meta Ads entries both under `ads`. Unique per `(customer_id, service_area, channel_label)`.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE |
| `service_area` | `text` | NO | | `seo`, `ads`, `social`, `email`, `website`, `creative`, `reporting`, `analytics` |
| `channel_label` | `text` | NO | | e.g. `Google Ads`, `Meta`, `Klaviyo` |
| `is_active` | `boolean` | NO | `true` | |
| `notes` | `text` | YES | | |
| `created_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `customer_service_channels_customer_id_service_area_channel__key` — `(customer_id, service_area, channel_label)` unique; `customer_service_channels_service_area_check` — service_area IN (seo, ads, social, email, website, creative, reporting, analytics)  
**Indexes:**
- `idx_customer_service_channels_customer` on `customer_id`
- `idx_customer_service_channels_partner` on `partner_id`

**RLS policies:** `partner_access` — ALL where `partner_id = app.current_partner_id`

---

### `customer_documents`
Versioned documents attached to a customer — audits, project docs, reports, and other collateral.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE |
| `document_type` | `text` | NO | | `project_doc`, `audit_context`, `audit_summary`, `report`, `other` |
| `name` | `text` | NO | | Display name of the document |
| `version` | `text` | NO | `'1.0'` | |
| `status` | `text` | NO | `'current'` | `current`, `stale`, `archived` |
| `content` | `text` | YES | | Body text; format determined by `content_format` |
| `content_format` | `text` | NO | `'markdown'` | `markdown`, `html`, `plaintext`, `json` |
| `metadata` | `jsonb` | YES | | Arbitrary structured metadata |
| `created_by_user_id` | `integer` | YES | | FK → `users.id` ON DELETE SET NULL |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `customer_documents_document_type_check` — document_type IN (project_doc, audit_context, audit_summary, report, other); `customer_documents_status_check` — status IN (current, stale, archived); `customer_documents_content_format_check` — content_format IN (markdown, html, plaintext, json)  
**Indexes:**
- `idx_customer_documents_partner` on `partner_id`
- `idx_customer_documents_type` on `(customer_id, document_type, status)`

**RLS policies:**
- `partner_access` — ALL where `partner_id = app.current_partner_id`
- `customer_read` — SELECT where `customer_id = app.current_customer_id AND partner_id = app.current_partner_id`

---

### `brand_voice`
One-row-per-customer brand voice profile. Stores tone descriptors, style rules, and example phrases used to guide AI content generation. Unique on `customer_id`.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE — unique |
| `tone_descriptors` | `text[]` | YES | | Array of adjectives e.g. `{friendly, authoritative}` |
| `voice_detail` | `text` | YES | | Freeform description of brand voice |
| `dos` | `text[]` | YES | | Writing guidelines — things to do |
| `donts` | `text[]` | YES | | Writing guidelines — things to avoid |
| `example_phrases` | `text[]` | YES | | Sample copy that reflects the brand voice |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `brand_voice_customer_id_key` — `customer_id` unique  
**Indexes:** `idx_brand_voice_partner` on `partner_id`  
**RLS policies:**
- `partner_access` — ALL where `partner_id = app.current_partner_id`
- `customer_read` — SELECT where `customer_id = app.current_customer_id AND partner_id = app.current_partner_id`

---

### `brand_voice_inputs`
Raw input submissions used to build or refine a customer's brand voice profile. Multiple rows per customer.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE |
| `input_type` | `text` | YES | | `seo`, `ads`, `social`, `email`, `website`, `creative`, `general` |
| `content` | `text` | NO | | The raw input text |
| `submitted_by` | `text` | YES | | Free-text attribution (name or role) |
| `notes` | `text` | YES | | Internal notes on the input |
| `created_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `chk_brand_voice_inputs_input_type` — input_type IN (seo, ads, social, email, website, creative, general)  
**Indexes:**
- `idx_brand_voice_inputs_customer` on `customer_id`
- `idx_brand_voice_inputs_partner` on `partner_id`

**RLS policies:** `partner_access` — ALL where `partner_id = app.current_partner_id`

---

### `target_audiences`
Defined audience segments for a customer. Multiple rows per customer, ordered by `rank`.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE |
| `name` | `text` | NO | | Audience segment name |
| `rank` | `integer` | NO | `99` | Display/priority order (lower = higher priority) |
| `demographics` | `jsonb` | YES | | Structured demographic attributes |
| `psychographics` | `jsonb` | YES | | Structured psychographic attributes |
| `buyer_stage` | `text` | YES | | `awareness`, `consideration`, `decision`, `retention` |
| `description` | `text` | YES | | Freeform description of the segment |
| `pain_points` | `text[]` | YES | | Array of pain point statements |
| `goals` | `text[]` | YES | | Array of goal statements |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `target_audiences_buyer_stage_check` — buyer_stage IN (awareness, consideration, decision, retention)  
**Indexes:**
- `idx_target_audiences_rank` on `(customer_id, rank)`
- `idx_target_audiences_partner` on `partner_id`

**RLS policies:**
- `partner_access` — ALL where `partner_id = app.current_partner_id`
- `customer_read` — SELECT where `customer_id = app.current_customer_id AND partner_id = app.current_partner_id`

---

### `info_base_entries`
Free-form knowledge base entries for a customer — facts, FAQs, key messages, and other context fed to AI generation.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE |
| `category` | `text` | YES | | Grouping label e.g. `faq`, `brand_story`, `awards` |
| `title` | `text` | NO | | Entry heading |
| `content` | `text` | NO | | Entry body |
| `is_key_message` | `boolean` | NO | `false` | Flagged entries are prioritised in AI prompts |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Indexes:**
- `idx_info_base_entries_customer` on `(customer_id, category)`
- `idx_info_base_entries_partner` on `partner_id`

**RLS policies:**
- `partner_access` — ALL where `partner_id = app.current_partner_id`
- `customer_read` — SELECT where `customer_id = app.current_customer_id AND partner_id = app.current_partner_id`

---

### `products_and_services`
Catalogue of products and services offered by a customer, used as context for AI content generation.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE |
| `name` | `text` | NO | | Product or service name |
| `type` | `text` | NO | | `product`, `service`, `bundle` |
| `description` | `text` | YES | | |
| `price_cents` | `integer` | YES | | Price in smallest currency unit |
| `currency` | `text` | YES | | ISO 4217 currency code e.g. `USD` |
| `price_model` | `text` | YES | | e.g. `one_time`, `monthly`, `annual`, `custom` |
| `url` | `text` | YES | | Link to the product/service page |
| `is_featured` | `boolean` | NO | `false` | Flagged entries are prioritised in AI prompts |
| `sort_order` | `integer` | NO | `0` | Display order |
| `metadata` | `jsonb` | YES | | Arbitrary structured metadata |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Constraints:** `products_and_services_type_check` — type IN (product, service, bundle)  
**Indexes:**
- `idx_products_and_services_customer` on `(customer_id, sort_order)`
- `idx_products_and_services_partner` on `partner_id`

**RLS policies:**
- `partner_access` — ALL where `partner_id = app.current_partner_id`
- `customer_read` — SELECT where `customer_id = app.current_customer_id AND partner_id = app.current_partner_id`

---

### `customer_contacts`
People at a customer organisation — contacts for reporting, billing, or general communication.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `serial` | NO | auto-increment | PK |
| `partner_id` | `integer` | NO | | FK → `partners.id` ON DELETE CASCADE |
| `customer_id` | `integer` | NO | | FK → `customers.id` ON DELETE CASCADE |
| `full_name` | `text` | NO | | |
| `title` | `text` | YES | | Job title |
| `email` | `text` | YES | | |
| `phone` | `text` | YES | | |
| `is_primary` | `boolean` | NO | `false` | Primary contact for the customer account |
| `receives_reports` | `boolean` | NO | `false` | Whether this contact receives automated reports |
| `notes` | `text` | YES | | Internal notes |
| `created_at` | `timestamptz` | NO | `now()` | |
| `updated_at` | `timestamptz` | NO | `now()` | |

**Indexes:**
- `idx_customer_contacts_customer` on `customer_id`
- `idx_customer_contacts_partner` on `partner_id`
- `idx_customer_contacts_primary` on `customer_id` WHERE `is_primary = true`

**RLS policies:** `partner_access` — ALL where `partner_id = app.current_partner_id`

---

## Relationships

```
plans
  └── partners                    (plan_id → plans.id)

industries
  └── customers                   (industry_id → industries.id)

partners
  └── customers                   (partner_id → partners.id)
  └── users                       (partner_id → partners.id)
  └── ai_token_usage              (partner_id → partners.id)
  └── partner_token_balance       (partner_id → partners.id)
  └── app_agents                  (partner_id → partners.id)
  └── blog_posts                  (partner_id → partners.id)
  └── customer_services           (partner_id → partners.id)
  └── customer_service_channels   (partner_id → partners.id)
  └── customer_documents          (partner_id → partners.id)
  └── brand_voice                 (partner_id → partners.id)
  └── brand_voice_inputs          (partner_id → partners.id)
  └── target_audiences            (partner_id → partners.id)
  └── info_base_entries           (partner_id → partners.id)
  └── products_and_services       (partner_id → partners.id)
  └── customer_contacts           (partner_id → partners.id)

customers
  └── users                       (customer_id → customers.id)
  └── ai_token_usage              (customer_id → customers.id)
  └── blog_posts                  (customer_id → customers.id)
  └── customer_services           (customer_id → customers.id)
  └── customer_service_channels   (customer_id → customers.id)
  └── customer_documents          (customer_id → customers.id)
  └── brand_voice                 (customer_id → customers.id)
  └── brand_voice_inputs          (customer_id → customers.id)
  └── target_audiences            (customer_id → customers.id)
  └── info_base_entries           (customer_id → customers.id)
  └── products_and_services       (customer_id → customers.id)
  └── customer_contacts           (customer_id → customers.id)

roles
  └── users                       (role_id → roles.id)
  └── role_permissions            (role_id → roles.id)

users
  └── ai_token_usage              (user_id → users.id)
  └── blog_posts                  (created_by_user_id → users.id)
  └── blog_posts                  (reviewer_user_id → users.id)
  └── blog_posts                  (published_by_user_id → users.id)
  └── blog_post_versions          (created_by_user_id → users.id)
  └── customer_documents          (created_by_user_id → users.id)

permissions
  └── role_permissions            (permission_id → permissions.id)

app_agents
  └── chat_sessions               (current_agent_key → app_agents.key)

users
  └── chat_sessions               (user_id → users.id)
  └── chat_session_shares         (shared_with_user_id → users.id)

chat_sessions
  └── chat_messages               (session_id → chat_sessions.id)
  └── chat_session_shares         (session_id → chat_sessions.id)

target_audiences
  └── blog_posts                  (target_audience_id → target_audiences.id)

blog_templates
  └── blog_posts                  (template_key → blog_templates.key)

blog_posts
  └── blog_post_versions          (post_id → blog_posts.id)
```
