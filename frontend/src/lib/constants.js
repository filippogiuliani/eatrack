// Values stored in the database: the visible names come from i18n
export const MEAL_TYPES = ['breakfast', 'lunch', 'snack', 'dinner'];
// Slots always shown in the diary (breakfast only appears when logged or planned)
export const DIARY_SLOTS = ['lunch', 'snack', 'dinner'];

export const AMOUNTS = ['full', 'half', 'puree', 'taste', 'refused'];

// How long a jar keeps, in days: warning and expired
export const LOCATIONS = [
  { id: 'fridge', warn: 2, expired: 3 },
  { id: 'freezer', warn: 30, expired: 90 },
  { id: 'pantry', warn: 60, expired: 180 },
];
export const locationInfo = (id) => LOCATIONS.find((l) => l.id === id) ?? LOCATIONS[0];

// Suggest the meal from the time of day
export function mealTypeForTime(d = new Date()) {
  const h = d.getHours();
  if (h < 10) return 'breakfast';
  if (h < 15) return 'lunch';
  if (h < 18) return 'snack';
  return 'dinner';
}
