export function getGrade(accuracy: number): string {
  if (accuracy >= 0.95) return 'S';
  if (accuracy >= 0.85) return 'A';
  if (accuracy >= 0.70) return 'B';
  if (accuracy >= 0.50) return 'C';
  return 'F';
}

export function getStars(accuracy: number): number {
  if (accuracy >= 0.95) return 5;
  if (accuracy >= 0.80) return 4;
  if (accuracy >= 0.65) return 3;
  if (accuracy >= 0.45) return 2;
  if (accuracy >= 0.25) return 1;
  return 0;
}
