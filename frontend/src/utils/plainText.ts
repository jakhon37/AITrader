/** Strip markdown from LLM narratives for plain-text UI surfaces. */
export function plainTextFromLlm(text: string): string {
  if (!text) return text;

  let cleaned = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  cleaned = cleaned.replace(/\*\*([^*]+)\*\*/g, '$1');
  cleaned = cleaned.replace(/\*([^*]+)\*/g, '$1');
  cleaned = cleaned.replace(/^#{1,6}\s+/gm, '');
  cleaned = cleaned.replace(/^[\s]*[-*•]\s+/gm, '');
  cleaned = cleaned.replace(/^\d+\.\s+/gm, '');
  cleaned = cleaned.replace(/\*+\s*$/g, '');
  cleaned = cleaned.replace(/[-•]\s*$/g, '');
  cleaned = cleaned.replace(/[ \t]+/g, ' ');
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');

  return cleaned.trim();
}