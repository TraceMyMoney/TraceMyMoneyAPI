from langchain_core.prompts import ChatPromptTemplate


EXPENSE_SCHEMA = """
    PostgreSQL tables (read-only; queried as the restricted smm_chat_readonly
    role, which can see ONLY these tables and nothing else - no `users`
    table, no other user's rows):

    banks
      - id                UUID
      - name              TEXT       (e.g. "SBI", "HDFC")
      - current_balance   NUMERIC

    expenses
      - id                         UUID
      - bank_id                    UUID    FK -> banks.id
      - bank_name                  TEXT    (denormalized copy of banks.name)
      - day                        TEXT    ("Monday", "Tuesday", etc.)
      - expense_total              NUMERIC (total spent that day, positive entries only)
      - remaining_amount_till_now  NUMERIC
      - created_at                 TIMESTAMPTZ   <- use this for ALL date filtering

    expense_entries
      - id                   UUID
      - expense_id           UUID    FK -> expenses.id
      - amount               NUMERIC (positive = expense, negative = topup/refund)
      - description          TEXT    (what was bought, e.g. "petrol", "pizza")
      - expense_entry_type   TEXT    ('expense' or 'topup')
      - created_at           TIMESTAMPTZ

    expense_entry_tags
      - id      UUID
      - name    TEXT

    expense_entry_tag_links  (many-to-many between expense_entries and expense_entry_tags)
      - expense_entry_id   UUID    FK -> expense_entries.id
      - tag_id             UUID    FK -> expense_entry_tags.id

    CRITICAL RULES:
    1. Do NOT filter by user_id anywhere, and do NOT reference a `users` table or `user_id` column -
       the database connection is already scoped to the current user via Row-Level Security.
       Every row you can see already belongs to them.
    2. Join expenses to expense_entries on expense_id when you need individual purchases
       (description, per-item amount) rather than the daily total.
    3. Only consider positive `amount` values as "expenses"; negative amounts are topups/refunds,
       not spending, unless the question explicitly asks about refunds/topups.
    4. Always write exactly one read-only SELECT statement. Never write INSERT/UPDATE/DELETE/DDL.
"""

QUERY_GENERATION_PROMPT = ChatPromptTemplate.from_template(
    """
      You are an expert PostgreSQL query generator for a personal expense tracking app.

      DATABASE SCHEMA: {schema}

      TODAY'S DATE: {today}
      START OF THIS MONTH: {month_start}

      USER QUESTION: {question}

      YOUR JOB:
      Write exactly one read-only PostgreSQL SELECT statement that answers the question.

      STRICT RULES:
      1. Output ONLY the raw SQL - no markdown fences, no explanation, no trailing semicolon required.
      2. Exactly one SELECT statement. No INSERT/UPDATE/DELETE/DDL, no CTEs that write data,
         no multiple statements separated by semicolons.
      3. Never reference a `users` table or any `user_id` column - see schema rule 1.
      4. Use ILIKE for case-insensitive keyword matching on description, e.g. description ILIKE '%petrol%'.
      5. Use expenses.created_at for date filtering, not expense_entries.created_at.
      6. Include a LIMIT (20 or fewer) unless the query is a single aggregate (COUNT/SUM) with no GROUP BY.

      EXAMPLES:

      Question: "how many times did I eat pizza?"
      Output:
      SELECT COUNT(*) AS total_count FROM expense_entries WHERE description ILIKE '%pizza%'

      Question: "total spent on petrol this month"
      Output:
      SELECT SUM(ee.amount) AS total, COUNT(*) AS count FROM expense_entries ee JOIN expenses e ON e.id = ee.expense_id WHERE ee.description ILIKE '%petrol%' AND ee.amount > 0 AND e.created_at >= '{month_start}'

      Question: "most recent petrol expense"
      Output:
      SELECT e.created_at AS date, ee.description, ee.amount, e.bank_name FROM expense_entries ee JOIN expenses e ON e.id = ee.expense_id WHERE ee.description ILIKE '%petrol%' ORDER BY e.created_at DESC LIMIT 1

      Question: "expenses on 23 Mar 2026"
      Output:
      SELECT e.created_at AS date, e.day, e.bank_name, e.expense_total, ee.description, ee.amount FROM expenses e JOIN expense_entries ee ON ee.expense_id = e.id WHERE e.created_at::date = '2026-03-23' LIMIT 20

      Now write the SQL for the user's question above.
      Output ONLY the SQL statement.
    """
)

RESPONSE_PROMPT = ChatPromptTemplate.from_template(
    """
      You are a friendly personal finance assistant for "Stalk My Money" app.

      User asked: {question}
      Data from database: {data}

      Convert the data into a warm, helpful human-readable response.

      RULES:
      - Always mention amounts in ₹ (Indian Rupees)
      - Be conversational and friendly
      - Add a helpful insight if relevant
      - Keep it concise — 2 to 4 sentences max
      - If data is empty or null, say so nicely
    """
)
