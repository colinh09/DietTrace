Extract the foods from this meal description into a JSON object.

Return ONLY JSON of the form:
{"items": [{"food": "<food name>", "quantity": <number>, "unit": "<unit>"}]}

Rules:
- One entry per distinct food.
- "food" is the bare food name (singular, no quantity words). Prefer the common
  whole-food name (e.g. "toast" -> "bread", a brand name -> its base food).
- "quantity" is a number ("half" -> 0.5, "a"/"an"/none -> 1).
- "unit" is the household measure ("slice", "cup", "each", ...); use "each" for
  whole countable items and "" when there is no natural unit.
- Do not invent foods that are not mentioned.

Meal description:
{text}
