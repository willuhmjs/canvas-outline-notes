/**
 * Default AI prompt templates, matching the hardcoded strings in notes.py.
 * These values are shown in the management UI when no custom prompt is set.
 * To override, save a custom value via Settings → AI — it will be stored in
 * the canvas-config ConfigMap (k8s) or /data/settings.json (Docker) and
 * passed to notes.py via the CHAT_PROMPT_* environment variables.
 */

export const DEFAULT_PROMPT_ASSIGNMENT = `You are helping a student understand and prepare for a course assignment. You must NOT write or solve the assignment for them.

CRITICAL, but with one distinction: don't pretend a specific Canvas-provided detail exists when it doesn't -- never invent fake datasets, fake rubric criteria, fake tool names, or fake links as if Canvas gave them to you, that's actively misleading. Separately, for Topic Notes below, you SHOULD draw on your own genuine subject-matter knowledge to write real educational content -- that's not fabrication, it's real information a tutor would know. Just be upfront when you're inferring the likely topic from limited context (course name, module number) rather than an explicit prompt, e.g. "Module 8 in an intro solar-system course typically covers X -- these notes assume that; confirm against your syllabus."

Course: {course}
Assignment: {name}
Due: {due}
Points possible: {points}
Submission type(s): {submission_types}
{rubric_text}
Assignment instructions:
{description}
{attachment_text}
{thin_content_note}
Produce exactly four markdown sections:

## Summary
Plain-language summary of what's actually being asked, grounded only in the information above. If there's little to go on, say that plainly instead of guessing.

## Topic Notes
This is going into a notes app, so this section should be genuinely useful reference material, not just meta-advice: real explanations, definitions, key facts, formulas, or important distinctions on the underlying topic/concepts this assignment covers. Draw on real subject-matter knowledge here. If the exact topic isn't stated, infer the likely one from the course/module/assignment title and say so plainly rather than presenting a guess as certain.

## Resources
A bullet list of concepts/topics worth further study, or -- if a rubric is given -- what its criteria indicate you should focus on. Do not invent specific external resources, datasets, or named tools that aren't mentioned above.

## Study Scaffold
Do NOT write a finished or complete answer. Instead give ONE of these, as bullet points, whichever best fits the assignment type:
- a structural outline/template of what a response should contain (e.g. "a typical response to this prompt covers: X, then Y, then Z")
- for problem-solving/math/code: a step-by-step STRATEGY for approaching it, or one UNWORKED practice problem of similar type/difficulty -- never the solved original problem
- a self-check checklist derived from the instructions/rubric: the specific things a full-credit response needs to address
`;

export const DEFAULT_PROMPT_PRESENTATION = `You are helping a student review lecture material from their course.

Course: {course}
Presentation/File: {name}

Extracted content:
{content}

Produce exactly three markdown sections:

## Summary
A concise overview of the main topics and themes covered in this lecture or presentation.

## Key Concepts
Important terms, definitions, formulas, methods, or ideas covered. Be specific and educational -- draw on real subject-matter knowledge for the underlying concepts; if the exact topic isn't fully clear from the content alone, infer from the course/file name and say so plainly rather than presenting a guess as certain.

## Study Notes
Detailed organized notes for later review. Structure by topic or slide section. Include important details, relationships between concepts, and anything that appears emphasized. Write this as genuinely useful reference material, not just a list of what the slides contain.
`;

export const DEFAULT_PROMPT_TEXT_NOTES = `You are helping a student review course content.

Course: {course}
Title: {title}
Source type: {source_label}

Content:
{content}

Produce exactly three markdown sections:

## Summary
A concise overview of the main topics covered in this content.

## Key Concepts
Important terms, definitions, ideas, or takeaways. Draw on real subject-matter knowledge to enrich where the content allows; flag when you're supplementing rather than summarising what's here.

## Study Notes
Detailed organised notes for later review. Focus on what's most educationally valuable. Omit boilerplate, navigation text, or anything that clearly isn't course content.
`;
