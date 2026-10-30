# Knowledge base — Charie restaurant demo

## Organization and data provenance

- `Northstar Kitchens Group` is an **invented multi-restaurant organization** for testing. `charie.organization_outlets` links every original restaurant to it. The original source models separate restaurants operating on a food-delivery marketplace, not a single real restaurant chain.
- Original **synthetic** source: DatabaseSample.com Food Delivery Sample Database **v2 (CC0)**. Sales, customers, menus, modifiers and deliveries are in the `public` schema, with order timestamps in **2024 and 2025**.
- Additional **synthetic** extension: `charie` schema. Recipes, ingredient quantities, labor cost, supplier relationships, waste, purchase orders, receipts and inventory are **generated estimates**, not measurements from the source business.
- Recipe ingredients are assigned by mapping each **dish name** to an estimated recipe template. Source menu categories are random relative to dishes (for example, "Cola" can sit under "Mains"), so never infer dish type from `menu_categories.name`. Never imply that these recipes were observed or confirmed.
- Weekly stock receipts are retrospectively generated to exactly cover each week's simulated consumption plus waste; supply patterns are not independently observed. Forecast accuracy cannot be evaluated on this simulated replenishment data.
- Currency: source prices are displayed in US dollars. Added ingredient unit costs and operating expenses are illustrative USD estimates.
- `charie.v_monthly_outlet_profit_estimate` is an **illustrative contribution**, not audited profit. Gross sales include tax and delivery fees and may not be directly comparable to net restaurant revenue. Do not call it actual net profit.

## Business relationships

- Each `public.orders` row has `restaurant_id`, `user_id`, `created_at`, `status`, `total_amount`.
- `public.order_items` joins `public.orders` via `order_id` and `public.menu_items` via `menu_item_id`. `public.menu_categories.restaurant_id` identifies which restaurant owns the menu.
- `charie.menu_recipes.menu_item_id` and `charie.recipe_ingredients` map sold items to estimated ingredients.
- `charie.modifier_ingredients` gives every source modifier option an estimated ingredient effect. Extras apply to every unit on the order line, while the source charges the modifier price only once per line.
- `charie.order_ingredient_usage` aggregates estimated ingredients **per order, restaurant, date and ingredient**. Query original line items and recipe estimates when explaining a spike.
- `charie.waste_events` records separately modeled wastage. It must not be counted as sales consumption.
- `charie.purchase_orders`, `charie.purchase_order_lines`, `charie.goods_receipts`, `charie.goods_receipt_lines` explain restocking.
- `charie.inventory_daily` is the daily stock ledger: `closing_qty = opening_qty + received_qty - used_qty - wasted_qty`.
- `charie.stock_policies` defines synthetic initial stock and reorder thresholds.
- `charie.labor_daily` and `charie.operating_expenses` are approximations for illustrative performance comparisons.
- `orders.total_amount` = round((Σ quantity × unit_price + Σ modifier prices) × (1 − coupon %), 2) + `tax_amount` (8% of the discounted subtotal) + `delivery_fee`.
- `charie.v_data_provenance` labels every table/view as `original_source`, `generated_simulation` or `derived_view`.
- Simulated stock never falls below `stock_policies.reorder_point_qty` (receipts are backfilled), so there are no historical stockouts to explain.

## Usage principles

- Do not invent an explanation if the dataset can't support it. Prefer showing the source SQL/query and caveats.
- When reporting cheese demand, state if numbers are **estimated recipe-based consumption**, not weighed real consumption.
- Always include explicit outlet, time range, units (g/ml/each), and whether a metric is source-generated or extension-simulated.
- Do not equate order count with order-item count.
- Never treat this dataset as current-day telemetry; source orders cover 2024–2025.
- Analyze recipes, modifier extras, waste events and deliveries independently when diagnosing high cheese use.
- Use read-only database credentials. Do not let an LLM issue unrestricted writes, execute SQL DDL, or manage credentials.
