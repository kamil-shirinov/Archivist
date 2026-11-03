// What each step of a live read says it does, in the words of the "Now" panel. The model it names is the one
// that ran the step: the step's own event carries it (Muse Glimmer on the step that recognises a page when
// Glimmer sorts it, Muse Spark when the page is classified from its image), and only where an event does not,
// the model of the step's usual role.

const IDLE = {
  snap: "Plain code moves each box onto the printed ink.",
  rules: "Plain code checks the values against the page’s own arithmetic.",
  decide: "Every value is accepted, or sent to a person.",
};

export function whatItDoes(step, model, names = {}) {
  const who = (role) => model || names[role] || "A model";
  switch (step) {
    case "recognise":
      return `${who("extractor")} is asked what kind of page this is.`;
    case "read":
      return `${who("extractor")} reads every value on the page and says where each one is.`;
    case "sam":
      return `${who("segmenter")} looks for stamps and stains that cover a value.`;
    case "blind":
      return `${who("rereader")} reads each value again, one cell at a time, without seeing the first answer.`;
    default:
      return IDLE[step] || "";
  }
}
