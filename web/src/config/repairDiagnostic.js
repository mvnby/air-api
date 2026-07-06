export const symptoms = [
  { value: 'not_cooling', label: 'Не охлаждает / слабо охлаждает' },
  { value: 'water_leak', label: 'Течет вода из внутреннего блока' },
  { value: 'not_turning_on', label: 'Не включается' },
  { value: 'turns_off', label: 'Сам выключается' },
  { value: 'noise_vibration', label: 'Шумит или вибрирует' },
  { value: 'bad_smell', label: 'Появился неприятный запах' },
  { value: 'error_code', label: 'На дисплее ошибка' },
  { value: 'other', label: 'Другая проблема' },
];

export const timings = [
  { value: 'immediately', label: 'Сразу после включения' },
  { value: 'after_minutes', label: 'Через несколько минут работы' },
  { value: 'after_hours', label: 'Через несколько часов' },
  { value: 'constantly', label: 'Постоянно' },
  { value: 'periodically', label: 'Периодически' },
  { value: 'after_service', label: 'После обслуживания / ремонта / переноса' },
  { value: 'unknown', label: 'Не знаю' },
];

export const clientChecks = [
  { value: 'filters_cleaned', label: 'Чистили фильтры' },
  { value: 'power_restarted', label: 'Перезагружали питание' },
  { value: 'remote_batteries_changed', label: 'Меняли батарейки в пульте' },
  { value: 'drainage_checked', label: 'Проверяли дренаж' },
  { value: 'master_visited', label: 'Уже приезжал мастер' },
  { value: 'nothing_checked', label: 'Ничего не проверяли' },
];

export const conditionalQuestions = {
  water_leak: [
    {
      key: 'leak_timing',
      label: 'Вода течет сразу или через некоторое время?',
      options: [
        { value: 'immediately', label: 'Сразу' },
        { value: 'later', label: 'Через некоторое время' },
        { value: 'unknown', label: 'Не знаю' },
      ],
    },
    {
      key: 'recently_cleaned',
      label: 'Кондиционер недавно чистили?',
      options: [
        { value: 'yes', label: 'Да' },
        { value: 'no', label: 'Нет' },
        { value: 'unknown', label: 'Не знаю' },
      ],
    },
    {
      key: 'drainage_exit',
      label: 'Куда выведен дренаж?',
      options: [
        { value: 'street', label: 'На улицу' },
        { value: 'sewer', label: 'В канализацию' },
        { value: 'unknown', label: 'Неизвестно' },
      ],
    },
    {
      key: 'leak_place',
      label: 'Где капает вода?',
      options: [
        { value: 'body', label: 'Из корпуса' },
        { value: 'wall', label: 'По стене' },
        { value: 'tube', label: 'Из трубки' },
      ],
    },
  ],
  not_cooling: [
    {
      key: 'indoor_fan_works',
      label: 'Вентилятор внутреннего блока работает?',
      options: [
        { value: 'yes', label: 'Да' },
        { value: 'no', label: 'Нет' },
        { value: 'unknown', label: 'Не знаю' },
      ],
    },
    {
      key: 'outdoor_unit_starts',
      label: 'Наружный блок запускается?',
      options: [
        { value: 'yes', label: 'Да' },
        { value: 'no', label: 'Нет' },
        { value: 'unknown', label: 'Не знаю' },
      ],
    },
    {
      key: 'freezing_seen',
      label: 'Есть ли обмерзание трубок или внутреннего блока?',
      options: [
        { value: 'yes', label: 'Да' },
        { value: 'no', label: 'Нет' },
        { value: 'unknown', label: 'Не знаю' },
      ],
    },
    {
      key: 'cooled_before',
      label: 'Кондиционер раньше охлаждал нормально?',
      options: [
        { value: 'yes', label: 'Да' },
        { value: 'no', label: 'Нет' },
        { value: 'unknown', label: 'Не знаю' },
      ],
    },
  ],
  not_turning_on: [
    {
      key: 'has_indication',
      label: 'Есть ли индикация на блоке?',
      options: [
        { value: 'yes', label: 'Да' },
        { value: 'no', label: 'Нет' },
        { value: 'unknown', label: 'Не знаю' },
      ],
    },
    {
      key: 'remote_response',
      label: 'Реагирует ли на пульт?',
      options: [
        { value: 'yes', label: 'Да' },
        { value: 'no', label: 'Нет' },
        { value: 'unknown', label: 'Не знаю' },
      ],
    },
    {
      key: 'power_checked',
      label: 'Проверяли ли питание / автомат?',
      options: [
        { value: 'yes', label: 'Да' },
        { value: 'no', label: 'Нет' },
      ],
    },
    {
      key: 'voltage_surge',
      label: 'Был ли скачок напряжения?',
      options: [
        { value: 'yes', label: 'Да' },
        { value: 'no', label: 'Нет' },
        { value: 'unknown', label: 'Не знаю' },
      ],
    },
  ],
  error_code: [
    {
      key: 'error_code',
      label: 'Введите код ошибки',
      type: 'text',
      placeholder: 'Например E6, F0, P4',
    },
  ],
};

export const photoFields = [
  {
    key: 'nameplate',
    label: 'Фото шильдика кондиционера',
    hint: 'Особенно важно фото шильдика: по нему можно определить модель, хладагент и часть технических параметров.',
  },
  { key: 'indoor_unit', label: 'Фото внутреннего блока целиком' },
  { key: 'outdoor_unit', label: 'Фото наружного блока, если доступен' },
  { key: 'error_display', label: 'Фото ошибки на дисплее, если есть' },
  { key: 'leak_place', label: 'Фото места протечки, если течет вода' },
];
