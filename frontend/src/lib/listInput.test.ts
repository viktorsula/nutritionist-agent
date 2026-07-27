import { describe, it, expect } from "vitest";
import { splitListInput, joinListInput } from "./listInput";

describe("splitListInput", () => {
  it("делит простой список по запятой", () => {
    expect(splitListInput("орехи, молоко")).toEqual(["орехи", "молоко"]);
  });

  it("сохраняет уточнение с запятой, если пункты разделены строками", () => {
    // Ядро P1-13: раньше это разваливалось на «молочные продукты» + «кроме козьего»,
    // то есть запрещало лишнее и теряло сам нюанс.
    expect(splitListInput("молочные продукты, кроме козьего\nглютен")).toEqual([
      "молочные продукты, кроме козьего",
      "глютен",
    ]);
  });

  it("не делит по запятой, когда есть переводы строки", () => {
    expect(splitListInput("а, б\nв, г")).toEqual(["а, б", "в, г"]);
  });

  it("делит по точке с запятой в однострочном вводе", () => {
    expect(splitListInput("орехи; молоко")).toEqual(["орехи", "молоко"]);
  });

  it("выбрасывает пустые элементы и пробелы", () => {
    expect(splitListInput("  орехи ,, молоко  ")).toEqual(["орехи", "молоко"]);
    expect(splitListInput("\n\n")).toEqual([]);
  });

  it("возвращает пустой список на не-строке и пустом вводе", () => {
    expect(splitListInput("")).toEqual([]);
    expect(splitListInput(null)).toEqual([]);
    expect(splitListInput(undefined)).toEqual([]);
    expect(splitListInput(42)).toEqual([]);
  });
});

describe("joinListInput", () => {
  it("склеивает по строке на пункт", () => {
    expect(joinListInput(["а", "б"])).toBe("а\nб");
  });

  it("переживает круговой обход без потери запятой внутри пункта", () => {
    // Если бы join шёл через запятую, повторное сохранение развалило бы пункт.
    const items = ["молочные продукты, кроме козьего", "глютен"];
    expect(splitListInput(joinListInput(items))).toEqual(items);
  });

  it("пустой список → пустая строка", () => {
    expect(joinListInput([])).toBe("");
    expect(joinListInput(null)).toBe("");
  });
});
