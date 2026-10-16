// Synthetic behavior for learning how to distinguish code from runtime evidence.
export function answerQuestion(question, documents) {
  const references = documents.filter(document => document.score >= 0.7).slice(0, 5);
  if (references.length === 0) {
    return { status: 'no-evidence', message: '没有找到足够相关的资料', citations: [] };
  }
  return { status: 'ready', question, citations: references.map(item => item.id) };
}
