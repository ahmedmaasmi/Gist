import { describe, expect, it } from "vitest";
import { clock, humanize, portraitSlug } from "./format";

describe("format", () => {
  it("formats clock times", () => {
    expect(clock(1260)).toBe("21:00");
    expect(clock(1305)).toBe("21:45");
  });

  it("matches the Python portrait file names in docs/art/portraits.csv", () => {
    expect(portraitSlug("Arsène Lupin")).toBe("arsene_lupin");
    expect(portraitSlug("C. Auguste Dupin")).toBe("c_auguste_dupin");
    expect(portraitSlug("Dr Hawley Crippen")).toBe("dr_hawley_crippen");
  });

  it("replaces IDs and minutes with names, rooms and times", () => {
    const lookup = { people: { suspect_02: "Count Dracula" }, rooms: { loc_cellar: "Wine Cellar" } };
    expect(humanize("Access/movement trace places suspect_02 at loc_cellar around minute 1300.", lookup)).toBe(
      "Access/movement trace places Count Dracula at Wine Cellar around 21:40.",
    );
    expect(humanize("I stayed in loc_cellar between 1320 and 1360.", lookup)).toBe(
      "I stayed in Wine Cellar between 22:00 and 22:40.",
    );
    expect(humanize("reliability 0.85 at 12 rooms", lookup)).toBe("reliability 0.85 at 12 rooms");
  });
});
