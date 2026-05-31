Extract the foods from this meal description into a JSON object.

Return ONLY JSON of the form:
{"items": [{"food": "<food name>", "quantity": <number>, "unit": "<unit>", "brand": "<brand>"}]}

Rules:
- One entry per distinct food.
- "food" is the bare food name (singular, no quantity words, no brand). Prefer the
  common whole-food name (e.g. "toast" -> "bread"). Keep the specific dish name
  for a prepared/restaurant item (e.g. "bacon cheeseburger", "burrito bowl").
- "quantity" is a number ("half" -> 0.5, "a"/"an"/none -> 1).
- "unit" is the household measure ("slice", "cup", "each", ...); use "each" for
  whole countable items and "" when there is no natural unit.
- "brand" is the restaurant or brand name when the user named one ("Five Guys",
  "Chipotle", "McDonald's", "Chobani"); use "" when none is mentioned. The brand
  goes in "brand", never in "food".
- Do not invent foods that are not mentioned.

Meal description:
{text}
