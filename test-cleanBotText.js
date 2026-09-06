#!/usr/bin/env node
// Test cleanBotText against real multi-line Meta contributor tier fixture
//
// RENDER PATHS THAT MUST CALL cleanBotText:
// 1. bubble() - chat bubbles (kind === "bot") ✅
// 2. card() - job cards for ops/think/research (kind.includes("bot")) ✅
// 3. renderBotMeta() - brief panel (org.staff/project.index) ✅
// 4. renderIndex() - generic brief render ✅
// 5. emptyStreamHtml() - empty stream state ✅
// 6. renderReportCard() - report card RESULT box + INDEX delta fields ✅
//
// If adding new render paths, wire cleanBotText or Meta junk will reappear.

function cleanBotText(text) {
  if (!text) return "";
  let cleaned = String(text);
  
  // Strip Meta contributor tier MULTILINE blocks: from !!! CONTRIBUTOR or "This is Meta's contributor tier"
  // through the entire paragraph including pricing URL, confidential warning, and "standard v" mention.
  // Use [\s\S]*? for non-greedy multiline match, stop at double newline or "Now:" INDEX marker.
  cleaned = cleaned.replace(/!!!?\s*CONTRIBUTOR\s+TIER[\s\S]*?(?:standard\s+v\d+[\s\S]*?(?=\n\n|Now:|Last:|Next:)|$)/gi, "");
  cleaned = cleaned.replace(/This\s+is\s+Meta'?s?\s+contributor\s+tier[\s\S]*?(?:standard\s+v\d+[\s\S]*?(?=\n\n|Now:|Last:|Next:)|$)/gi, "");
  
  // Strip mid-line CONTRIBUTOR mentions (INDEX Last: lines)
  cleaned = cleaned.replace(/CONTRIBUTOR\s+TIER\s*—\s*TRAINS?\s+ON\s+YOUR\s+DATA/gi, "");
  
  // Strip orphan fragments that survived multiline removal
  cleaned = cleaned.replace(/prompts\s+and\s+completions\s+to\s+train\s+future\s+Meta\s+models\.?/gi, "");
  cleaned = cleaned.replace(/See\s+current\s+pricing\s+and\s+rate\s+limits\s+for\s+the\s+Meta\s+Model\s+API[\s\S]*?https?:\/\/[^\s]+/gi, "");
  cleaned = cleaned.replace(/https?:\/\/dev\.meta\.ai\/docs\/pricing-rate-limits?\/?/gi, "");
  cleaned = cleaned.replace(/Do\s+NOT\s+use\s+it\s+for\s+confidential,\s+proprietary,\s+personal,\s+or\s+otherwise\s+sensitive\s+data\.?/gi, "");
  cleaned = cleaned.replace(/For\s+the\s+same\s+model\s+with\s+no\s+training\s+on\s+your\s+data[\s\S]*?(?=\n\n|Now:|Last:|Next:|$)/gi, "");
  cleaned = cleaned.replace(/It\s+lowers\s+the\s+barrier\s+to\s+entry[\s\S]*?acceptable\./gi, "");
  
  // Strip Meta CLI banner artifacts
  cleaned = cleaned.replace(/security\.allow_data_training_tiers_noninteractive/gi, "");
  cleaned = cleaned.replace(/[┌┐└┘│─]+\s*Scheduled\s+Jobs\s*[┌┐└┘│─]+/gi, "");
  
  // Strip standalone Meta Model API pricing boilerplate
  cleaned = cleaned.replace(/Meta\s+Model\s+API\s+is\s+free[\s\S]*?https?:\/\/dev\.meta\.ai\/docs\/pricing-rate-limits?\/?/gi, "");
  
  // Only strip single-line SMOKE test patterns
  const lines = cleaned.split('\n').map(line => line.trim()).filter(line => line.length > 0);
  if (lines.length === 1 && /^SMOKE\d+_[A-Z_]+$/i.test(lines[0])) {
    return "";
  }
  
  // Collapse multiple blank lines
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
  
  return cleaned.trim();
}

// Real fixture from /api/jobs showing multi-line Meta contributor tier block
const fixture = `!!! CONTRIBUTOR TIER — TRAINS ON YOUR DATA !!!

This is Meta's contributor tier. Selecting it permits Meta to use your
prompts and completions to train future Meta models.

See current pricing and rate limits for the Meta Model API here:
  https://dev.meta.ai/docs/pricing-rate-limits/

It lowers the barrier to entry for
prototyping, testing integrations, and
scaling experiments where training on your
data is acceptable. Do NOT use it
for confidential, proprietary, personal, or
otherwise sensitive data. For the
same model with no training on your data, select the standard v`;

const cleaned = cleanBotText(fixture);

console.log("=== FIXTURE ===");
console.log(fixture);
console.log("\n=== CLEANED ===");
console.log(cleaned);
console.log("\n=== TESTS ===");

const hasMeta = /meta/i.test(cleaned);
const hasContributor = /contributor/i.test(cleaned);
const hasPricing = /pricing-rate/i.test(cleaned);
const hasConfidential = /confidential/i.test(cleaned);
const hasPrompts = /prompts\s+and\s+completions/i.test(cleaned);
const hasTraining = /training\s+on\s+your\s+data/i.test(cleaned);

console.log(`HAS_META: ${hasMeta}`);
console.log(`HAS_CONTRIBUTOR: ${hasContributor}`);
console.log(`HAS_PRICING: ${hasPricing}`);
console.log(`HAS_CONFIDENTIAL: ${hasConfidential}`);
console.log(`HAS_PROMPTS: ${hasPrompts}`);
console.log(`HAS_TRAINING: ${hasTraining}`);

const allClean = !hasMeta && !hasContributor && !hasPricing && !hasConfidential && !hasPrompts && !hasTraining;
console.log(`\nALL_CLEAN: ${allClean}`);

if (!allClean) {
  console.error("\n❌ FAIL: Meta leftovers detected");
  process.exit(1);
}

console.log("\n✅ PASS: All Meta junk stripped");
process.exit(0);
