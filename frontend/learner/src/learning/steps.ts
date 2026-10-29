// The 12 learning steps (architecture 02, "The learning steps"). The design
// shows 11; 02's 12 win (it adds steps 4 and 9 and has no "Use your answers").
// Phase 7 uses the same numbers.
export interface LearningStepDef {
  label: string;
  phrase: string;
}

export const LEARNING_STEPS: LearningStepDef[] = [
  { label: "Read your notes", phrase: "reading your notes" },
  { label: "Study the database structure", phrase: "studying the database structure" },
  { label: "Look at the data itself", phrase: "looking at the data itself" },
  { label: "Find how tables connect", phrase: "finding how tables connect" },
  { label: "Read the documents", phrase: "reading the documents" },
  { label: "Pull facts from the documents", phrase: "pulling facts from the documents" },
  { label: "Explain each table", phrase: "explaining each table" },
  { label: "Build and test business numbers", phrase: "building and testing business numbers" },
  { label: "Work out default meanings", phrase: "working out default meanings" },
  { label: "Ask you questions", phrase: "writing questions for you" },
  { label: "Test itself", phrase: "testing itself" },
  { label: "Go live", phrase: "getting ready to go live" },
];
