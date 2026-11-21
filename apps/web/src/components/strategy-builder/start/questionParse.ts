import {
  MAX_QUESTIONS,
  parseDraftQuestions,
  type DraftAsk,
  type DraftQuestion,
} from '../../agent/draftQuestions';

const NUMBERED = /^\s*(?:#+\s*)?(?:\*\*)?(?:Q(?:uestion)?\s*)?(\d+)[.):]\s*(?:\*\*)?\s*(.+)$/i;
const BULLET = /^\s*(?:[-*•]|[a-e][.)]|\(\w\))\s+(.+)$/;
const PICK =
  /\s*\((?:my pick|i'?d pick|i would pick|recommended|default|suggested)\)|\s*[-–]\s*(?:my pick|recommended|default)\b/i;
const OPTIONS_LEAD = /^(?:options?|choices?|for example|e\.g\.)\s*:\s*/i;

const clean = (s: string) =>
  s
    .replace(/\*\*|__|`/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[.;,]$/, '');

/** "A, B, or C" and "A or B" into their parts; one part when there is no list. */
export function splitAlternatives(text: string): string[] {
  const t = clean(text).replace(/\?$/, '');
  if (!/\bor\b/i.test(t)) return [t];
  const parts = t
    .split(/,\s*(?:or\s+)?|\s+or\s+/i)
    .map((p) => clean(p))
    .filter(Boolean);
  return parts.length >= 2 ? parts : [t];
}

interface Draft {
  label: string;
  help: string[];
  options: string[];
  preset: string | null;
}

function addOption(q: Draft, raw: string) {
  const picked = PICK.test(raw);
  const text = clean(raw.replace(PICK, ''));
  if (!text || q.options.includes(text)) return;
  q.options.push(text);
  if (picked && q.preset === null) q.preset = text;
}

/**
 * Reads numbered questions from a prose reply: options as bullets under a question, or as
 * "A, B or C" after it. An option marked "(my pick)" is preset; otherwise the first one is.
 * Questions with fewer than two options are dropped. Null when none are left.
 */
export function parseProseQuestions(content: string): DraftAsk | null {
  const intro: string[] = [];
  const found: Draft[] = [];
  let current: Draft | null = null;
  for (const line of content.split('\n')) {
    if (!line.trim()) continue;
    const numbered = NUMBERED.exec(line);
    if (numbered) {
      const body = numbered[2];
      const q = body.indexOf('?');
      current = {
        label: clean(q >= 0 ? body.slice(0, q + 1) : body),
        help: [],
        options: [],
        preset: null,
      };
      found.push(current);
      const rest = q >= 0 ? body.slice(q + 1).replace(OPTIONS_LEAD, '') : '';
      if (rest.trim()) {
        const alts = splitAlternatives(rest);
        if (alts.length >= 2) alts.forEach((a) => current && addOption(current, a));
        else current.help.push(clean(rest));
      }
      continue;
    }
    if (!current) {
      intro.push(line.trim());
      continue;
    }
    const bullet = BULLET.exec(line);
    if (bullet) {
      addOption(current, bullet[1]);
      continue;
    }
    const lead = line.trim();
    if (OPTIONS_LEAD.test(lead)) {
      splitAlternatives(lead.replace(OPTIONS_LEAD, '')).forEach(
        (a) => current && addOption(current, a)
      );
    } else if (current.options.length === 0) {
      current.help.push(clean(lead));
    }
  }
  const questions: DraftQuestion[] = found
    .filter((q) => q.label && q.options.length >= 2)
    .slice(0, MAX_QUESTIONS)
    .map((q, i) => ({
      id: `q${i + 1}`,
      label: q.label,
      help: q.help.join(' '),
      short: q.label,
      options: q.options,
      preset: q.preset ?? q.options[0],
    }));
  if (questions.length === 0) return null;
  return { intro: intro.join(' '), questions };
}

/** The questions in a reply: the structured block when there is one, else the prose. */
export function readDraftQuestions(content: string): DraftAsk | null {
  return parseDraftQuestions(content) ?? parseProseQuestions(content);
}
