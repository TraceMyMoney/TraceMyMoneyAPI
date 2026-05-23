from langchain_core.prompts import ChatPromptTemplate


EXPENSE_SCHEMA = """
    MongoDB Database: <>

    Collection: expense
    Each document = ONE DAY of expenses for a user.

    ROOT LEVEL FIELDS (never prefix with "expenses."):
      - _id                       : ObjectId
      - user_id                   : ObjectId  ← ALWAYS filter by this
      - day                       : string    ("Monday", "Tuesday" etc.)
      - bank_name                 : string    ("SBI", "HDFC" etc.) ← ROOT ONLY
      - expense_total             : number    (total ₹ spent that day) ← ROOT ONLY
      - remaining_amount_till_now : number    (remaining ₹ balance)
      - created_at                : ISODate   ← USE THIS FOR ALL DATE FILTERING

    expenses ARRAY (use $unwind to access individual items):
      - expenses.amount       : number  (₹ amount of single item)
      - expenses.description  : string  (what was bought e.g. "petrol", "pizza")
      - expenses.ee_id        : number
      - expenses.created_at   : ISODate ← DO NOT use this for date filtering

    CRITICAL RULES:
    1. bank_name      → ROOT field, NEVER write expenses.bank_name
    2. expense_total  → ROOT field, NEVER write expenses.expense_total
    3. Date filtering → ALWAYS use ROOT created_at, NEVER expenses.created_at
    4. After $unwind  → bank_name is still "bank_name" NOT "expenses.bank_name"
    5. user_id        → ALWAYS include in $match as string: "user_id": "<user_id>"
    6. expenses.amount → DO NOT consider the negative amount, only consider the amount 

    Example document:
    {
      "user_id": ObjectId("676d8ba24b77cfc402f66ed0"),
      "day": "Tuesday",
      "bank_name": "SBI",                ← ROOT
      "expense_total": 500,              ← ROOT
      "remaining_amount_till_now": 2000,
      "created_at": ISODate("2026-03-24"),  ← ROOT - use for date filtering
      "expenses": [
        {
          "amount": 300,                 ← INSIDE ARRAY
          "description": "petrol",      ← INSIDE ARRAY
          "created_at": ISODate("2026-03-24")  ← DO NOT use for date filter
        },
        {
          "amount": 200,
          "description": "pizza"
        }
      ]
    }
"""

QUERY_GENERATION_PROMPT = ChatPromptTemplate.from_template(
    """
      You are an expert MongoDB aggregation pipeline generator for a personal expense tracking app.

      DATABASE SCHEMA: {schema}

      USER ID: {user_id}
      TODAY'S DATE: {today}

      USER QUESTION: {question}

      YOUR JOB:
      Generate a MongoDB aggregation pipeline to answer the user's question.

      STRICT RULES:
      1. ALWAYS start pipeline with:
        {{"$match": {{"user_id": "{user_id}"}}}}
      2. ALL MongoDB operators MUST have $ prefix: $match, $group, $unwind, $sort, $limit, $project, $sum, $gte, $lte, $gt, $lt, $eq, $regex
      3. For date ranges use:
        {{"$gte": {{"$date": "YYYY-MM-DDT00:00:00Z"}}, "$lte": {{"$date": "YYYY-MM-DDT23:59:59Z"}}}}
      4. For keyword search use:
        {{"expenses.description": {{"$regex": "keyword", "$options": "i"}}}}
      5. bank_name and expense_total are ROOT fields — NEVER prefix with "expenses."
      6. Use $unwind ONLY when accessing individual expense items
      7. Return ONLY raw JSON array — no markdown, no backticks, no explanation

      DATE RULES:
      - "today"       → created_at >= today 00:00:00
      - "this week"   → created_at >= monday of current week
      - "this month"  → created_at >= first day of current month
      - "last N days" → created_at >= today minus N days
      - "23 Mar 2026" → created_at gte 2026-03-23T00:00:00Z lte 2026-03-23T23:59:59Z

      EXAMPLES:

      Question: "how many times did I eat pizza?"
      Output:
      [{{"$match":{{"user_id":"{user_id}"}}}},{{"$unwind":"$expenses"}},{{"$match":{{"expenses.description":{{"$regex":"pizza","$options":"i"}}}}}},{{"$count":"total_count"}}]

      Question: "total spent on petrol this month"
      Output:
      [{{"$match":{{"user_id":"{user_id}","created_at":{{"$gte":{{"$date":"{month_start}"}}}}}}}},{{"$unwind":"$expenses"}},{{"$match":{{"expenses.description":{{"$regex":"petrol","$options":"i"}}}}}},{{"$group":{{"_id":null,"total":{{"$sum":"$expenses.amount"}},"count":{{"$sum":1}}}}}}]

      Question: "most recent petrol expense"
      Output:
      [{{"$match":{{"user_id":"{user_id}"}}}},{{"$unwind":"$expenses"}},{{"$match":{{"expenses.description":{{"$regex":"petrol","$options":"i"}}}}}},{{"$sort":{{"created_at":-1}}}},{{"$limit":1}},{{"$project":{{"date":"$created_at","description":"$expenses.description","amount":"$expenses.amount","bank_name":1,"_id":0}}}}]

      Question: "expenses on 23 Mar 2026"
      Output:
      [{{"$match":{{"user_id":"{user_id}","created_at":{{"$gte":{{"$date":"2026-03-23T00:00:00Z"}},"$lte":{{"$date":"2026-03-23T23:59:59Z"}}}}}}}},{{"$project":{{"date":"$created_at","day":1,"bank_name":1,"expense_total":1,"expenses":1,"_id":0}}}}]

      Now generate the pipeline for the user's question above.
      Output ONLY the JSON array.
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
