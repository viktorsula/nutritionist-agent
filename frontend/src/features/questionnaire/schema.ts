/**
 * Единое определение опросника онбординга (6 шагов, ~37 полей).
 * Используется и формой, и сабмитом. Полный текст ответов → questionnaire_json;
 * ключевые поля дополнительно мапятся в колонки client_profiles / measurements.
 */

export type FieldType =
  | "text"
  | "textarea"
  | "number"
  | "date"
  | "time"
  | "select"
  | "multiselect"
  | "yesno"
  | "yesno_text"
  | "file";

export interface Bilingual {
  ru: string;
  en: string;
}

export interface Option {
  value: string;
  label: Bilingual;
}

export interface Field {
  id: string;
  type: FieldType;
  label: Bilingual;
  required?: boolean;
  options?: Option[];
  unit?: string;
  multiple?: boolean; // для file
}

export interface Step {
  id: string;
  title: Bilingual;
  fields: Field[];
}

const GENDER: Option[] = [
  { value: "male", label: { ru: "Мужской", en: "Male" } },
  { value: "female", label: { ru: "Женский", en: "Female" } },
  { value: "other", label: { ru: "Другое", en: "Other" } },
];

const WORK_ACTIVITY: Option[] = [
  { value: "sedentary", label: { ru: "Сидячая", en: "Sedentary" } },
  { value: "mixed", label: { ru: "Смешанная", en: "Mixed" } },
  { value: "active", label: { ru: "Активная", en: "Active" } },
];

const SPORT_LEVEL: Option[] = [
  { value: "none", label: { ru: "Нет", en: "None" } },
  { value: "low", label: { ru: "Низкий", en: "Low" } },
  { value: "medium", label: { ru: "Средний", en: "Medium" } },
  { value: "high", label: { ru: "Высокий", en: "High" } },
];

const EATING_OUT: Option[] = [
  { value: "home", label: { ru: "В основном дома", en: "Mostly home" } },
  { value: "mixed", label: { ru: "Смешанно", en: "Mixed" } },
  { value: "out", label: { ru: "В основном вне дома", en: "Mostly out" } },
];

const COLD_FREQ: Option[] = [
  { value: "rare", label: { ru: "Редко", en: "Rarely" } },
  { value: "few_year", label: { ru: "Несколько раз в год", en: "A few times a year" } },
  { value: "often", label: { ru: "Часто", en: "Often" } },
];

const ENVIRONMENT: Option[] = [
  { value: "healthy", label: { ru: "Больше здорового питания", en: "Mostly healthy" } },
  { value: "mixed", label: { ru: "Смешанно", en: "Mixed" } },
  { value: "unhealthy", label: { ru: "Больше нездорового", en: "Mostly unhealthy" } },
];

const FAMILY_SUPPORT: Option[] = [
  { value: "supportive", label: { ru: "Поддерживают", en: "Supportive" } },
  { value: "neutral", label: { ru: "Нейтрально", en: "Neutral" } },
  { value: "unsupportive", label: { ru: "Не разделяют", en: "Unsupportive" } },
];

export const IMPROVE: Option[] = [
  { value: "health", label: { ru: "Здоровье", en: "Health" } },
  { value: "weight", label: { ru: "Вес", en: "Weight" } },
  { value: "appearance", label: { ru: "Внешние аспекты", en: "Appearance" } },
];

export const QUESTIONNAIRE: Step[] = [
  {
    id: "personal",
    title: { ru: "Личные данные и замеры", en: "Personal data & measurements" },
    fields: [
      { id: "full_name", type: "text", label: { ru: "ФИО", en: "Full name" }, required: true },
      { id: "birth_date", type: "date", label: { ru: "Дата рождения", en: "Date of birth" }, required: true },
      { id: "gender", type: "select", label: { ru: "Пол", en: "Gender" }, required: true, options: GENDER },
      { id: "weight", type: "number", label: { ru: "Вес", en: "Weight" }, unit: "кг", required: true },
      { id: "height", type: "number", label: { ru: "Рост", en: "Height" }, unit: "см", required: true },
      { id: "target_weight", type: "number", label: { ru: "Желаемый вес", en: "Target weight" }, unit: "кг" },
      { id: "neck", type: "number", label: { ru: "Объём шеи", en: "Neck" }, unit: "см" },
      { id: "waist", type: "number", label: { ru: "Объём талии", en: "Waist" }, unit: "см" },
      { id: "hips", type: "number", label: { ru: "Объём бёдер", en: "Hips" }, unit: "см" },
    ],
  },
  {
    id: "lifestyle",
    title: { ru: "Образ жизни", en: "Lifestyle" },
    fields: [
      { id: "weight_history", type: "textarea", label: { ru: "Как давно в этом весе и как он менялся за 3–5 лет", en: "How long at this weight; how it changed over 3–5 years" } },
      { id: "daily_routine", type: "textarea", label: { ru: "Режим дня", en: "Daily routine" } },
      { id: "bedtime", type: "time", label: { ru: "Во сколько ложитесь спать", en: "Bedtime" } },
      { id: "wakeup", type: "time", label: { ru: "Во сколько просыпаетесь", en: "Wake-up time" } },
      { id: "work_field", type: "text", label: { ru: "Сфера работы", en: "Field of work" } },
      { id: "work_activity", type: "select", label: { ru: "Активность на работе", en: "Activity at work" }, options: WORK_ACTIVITY },
      { id: "outdoor_hours_week", type: "number", label: { ru: "Часов на воздухе в неделю", en: "Outdoor hours per week" } },
      { id: "sport_level", type: "select", label: { ru: "Спорт/физнагрузки — уровень", en: "Sport/activity level" }, options: SPORT_LEVEL },
      { id: "sport_details", type: "textarea", label: { ru: "Спорт — подробно (когда, какой, как давно)", en: "Sport — details (when, what, how long)" } },
    ],
  },
  {
    id: "nutrition",
    title: { ru: "Питание", en: "Nutrition" },
    fields: [
      { id: "diet_typical", type: "textarea", label: { ru: "Рацион: 2–3 дня (будни и выходной) подробно, с временем приёмов пищи", en: "Diet: 2–3 days (weekday & weekend) in detail, with meal times" }, required: true },
      { id: "water_liters", type: "number", label: { ru: "Сколько воды в день", en: "Water per day" }, unit: "л" },
      { id: "other_drinks", type: "textarea", label: { ru: "Другие напитки и сколько за день", en: "Other drinks and amounts per day" } },
      { id: "alcohol", type: "textarea", label: { ru: "Алкоголь: как часто и какой", en: "Alcohol: how often and what" } },
      { id: "eating_out", type: "select", label: { ru: "Питание дома или в общепите", en: "Eating at home or out" }, options: EATING_OUT },
    ],
  },
  {
    id: "health",
    title: { ru: "Здоровье", en: "Health" },
    fields: [
      { id: "chronic_conditions", type: "textarea", label: { ru: "Хронические заболевания (как справляетесь, как долго)", en: "Chronic conditions (how you manage, how long)" } },
      { id: "body_complaints", type: "textarea", label: { ru: "Жалобы на состояние тела", en: "Body complaints" } },
      { id: "unpleasant_symptoms", type: "textarea", label: { ru: "Неприятные симптомы по здоровью", en: "Unpleasant health symptoms" } },
      { id: "serious_illness_surgery", type: "textarea", label: { ru: "Серьёзные заболевания или операции", en: "Serious illnesses or surgeries" } },
      { id: "cold_frequency", type: "select", label: { ru: "Как часто болеете простудными", en: "How often you catch colds" }, options: COLD_FREQ },
      { id: "stress", type: "textarea", label: { ru: "Стресс/настроение: как часто и как долго", en: "Stress/mood: how often and how long" } },
      { id: "under_doctor", type: "yesno_text", label: { ru: "Состоите на учёте у врача? Если да — причина", en: "Under a doctor's supervision? If yes — reason" } },
    ],
  },
  {
    id: "meds_labs",
    title: { ru: "Препараты и анализы", en: "Medications & lab tests" },
    fields: [
      { id: "medications", type: "textarea", label: { ru: "Препараты (какие, как долго, включая обезболивающие)", en: "Medications (which, how long, incl. painkillers)" } },
      { id: "supplements", type: "textarea", label: { ru: "Витамины/добавки (какие, дозировки, почему / когда последний раз)", en: "Vitamins/supplements (which, doses, why / when last)" } },
      { id: "doctor_recommendations", type: "textarea", label: { ru: "Рекомендации лечащего врача (период, какие)", en: "Doctor's recommendations (period, which)" } },
      { id: "last_labs_date", type: "date", label: { ru: "Когда последний раз сдавали анализы", en: "When you last did lab tests" } },
      { id: "labs_files", type: "file", label: { ru: "Прикрепить анализы (PDF, если не позже 6 мес.)", en: "Attach lab results (PDF, if within 6 months)" }, multiple: true },
      { id: "allergies", type: "yesno_text", label: { ru: "Аллергия на продукты? Если да — какие (каждую с новой строки)", en: "Food allergies? If yes — which (one per line)" } },
      { id: "intolerances", type: "yesno_text", label: { ru: "Непереносимость продуктов? Если да — какие (каждую с новой строки)", en: "Food intolerances? If yes — which (one per line)" } },
      { id: "smoking", type: "yesno_text", label: { ru: "Курите? Если да — сколько и как давно", en: "Do you smoke? If yes — how much and how long" } },
    ],
  },
  {
    id: "context_goals",
    title: { ru: "Контекст и цели", en: "Context & goals" },
    fields: [
      { id: "environment_eating", type: "select", label: { ru: "Окружение: больше здорового питания или наоборот", en: "Environment: more healthy eating or not" }, options: ENVIRONMENT },
      { id: "family_support", type: "select", label: { ru: "Семья/близкие поддерживают ЗОЖ", en: "Family supports a healthy lifestyle" }, options: FAMILY_SUPPORT },
      { id: "frequent_complaints", type: "textarea", label: { ru: "Наиболее частые жалобы на здоровье", en: "Most frequent health complaints" } },
      { id: "additional_info", type: "textarea", label: { ru: "Дополнительная информация, важная для плана", en: "Additional info important for the plan" } },
      { id: "improve_targets", type: "multiselect", label: { ru: "Что хотите улучшить", en: "What you want to improve" }, required: true, options: IMPROVE },
      { id: "goal_text", type: "textarea", label: { ru: "Что именно хотите улучшить (свободно)", en: "What exactly you want to improve (free text)" } },
    ],
  },
];

/** Плоский список всех полей — для сабмита/валидации. */
export const ALL_FIELDS: Field[] = QUESTIONNAIRE.flatMap((s) => s.fields);
