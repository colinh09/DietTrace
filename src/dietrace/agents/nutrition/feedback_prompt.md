Interpret the user's feedback about their logged meal and return a JSON object describing the action to take.

Current meal items:
{meal_items}

User feedback:
{feedback_text}

Return ONLY JSON of the form:
{"kind": "<kind>", "target_food": "<food name or empty>", "adjustment": <number or null>, "target_grams": <number or null>, "scope": "<scope>", "rationale": "<why>"}

Rules for "kind":
- "portion_adjust": the user says the amount of a food is wrong (too much / too little). Set "target_food" to the food name. Then EITHER:
  - If the user gives an ABSOLUTE amount ("about 30 grams", "two tablespoons" ≈ 32 g, "a cup" ≈ 240 g), set "target_grams" to that gram weight and leave "adjustment" null. Convert common household units to grams.
  - If the user gives a RELATIVE amount ("half", "a third", "way too much", "double"), set "adjustment" to the multiplier of the current grams (0.5 = half, 0.33 = a third, 2.0 = double) and leave "target_grams" null.
  Never express an absolute gram amount as a multiplier.
- "remove_item": the user says they did not eat a food at all. Set "target_food" to that food name. Set "adjustment" to null.
- "add_item": the user says they ate something not in the list. Set "target_food" to that food name. Set "adjustment" to the estimated grams (or null if unknown).
- "standing_rule": the user is stating a preference that applies to a class of meals or a meal type (e.g. "from now on", "whenever I log this", a macro target). Set "target_food" to "" and "adjustment" to the gram target if given (else null).

Rules for "scope":
- "this_food": applies only to one food in this meal.
- "this_meal": applies to the whole meal logged right now.
- "meal_type": applies to a class of meals (preworkout, breakfast, etc.) or is a standing preference.

"rationale" is a short plain-English explanation of what the user meant.
