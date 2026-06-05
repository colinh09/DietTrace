List the foods in this meal as JSON.

Return: {"items": [{"food": "<name>", "quantity": <number>, "unit": "<unit>", "brand": "<brand>"}]}

Guidelines:
- Each distinct food or ingredient gets its own entry.
- Use a clear, common name for the food. If the user named a brand or restaurant,
  put that in "brand" and leave it out of "food".
- Convert text quantities to numbers: "half" → 0.5, "a", "one", or no quantity → 1,
  "couple" → 2, "few" → 3.
- Use a natural unit where it helps (e.g. "cup", "slice", "tablespoon", "piece");
  leave "unit" blank when there is no natural one.
- Only list foods the user actually mentioned.

Meal:
{text}
