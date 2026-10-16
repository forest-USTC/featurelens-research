// Synthetic sample. This file is analyzed, never launched by the workbench.
import { ipcMain } from 'electron';
import { answerQuestion } from './retrieval.js';
ipcMain.handle('knowledge:ask', async (_event, question, documents) => {
  return answerQuestion(question, documents);
});
