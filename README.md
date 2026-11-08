# База знань Muliprocessing-Analisis

Це довговічна пам’ять про систему пакетного аналізу аудіо та фактичну реалізацію MLT-5. Вона живе лише в orphan-гілці `kb-only` і відновлюється як linked worktree того самого локального Git-репозиторію. Гілка `main` містить код; у дереві `kb-only` зберігаються лише документи цієї KB.

## Карта документів

| Документ | Для чого його читати / що в ньому підтримувати |
| --- | --- |
| [status.md](status.md) | Поточна перевірена точка, виконане, невідоме, відкриті рішення й наступна дія. Починай із нього. |
| [collaboration.md](collaboration.md) | Обов’язковий pull/edit/merge/push workflow для агентів, паралельних worktree та автоматичного розв’язання конфліктів KB. |
| [jira.md](jira.md) | Перевірена Jira identity MLT, API/board verification, правила live-status і безпечного зіставлення з кодом. |
| [architecture.md](architecture.md) | Призначення системи, відповідальність MLT-1…MLT-5, рекомендований потік і теоретичні обмеження. |
| [backlog.md](backlog.md) | Карта епіків, User Stories, пов’язаних технічних задач і датованих Jira-знімків із наданих звітів. |
| [data_contract.md](data_contract.md) | Поля, типи, одиниці, інваріанти, помилки, версії та правила передачі масивів між модулями/процесами. |
| [system.md](system.md) | Фактичні API, алгоритми та обмеження коду, що існує в `main`. |
| [testing.md](testing.md) | Тест-план, усі 12 кейсів PR3, 18 пунктів checklist, критерії й чотири непідтверджені bug reports PR4. |
| [decisions.md](decisions.md) | Прийняті технічні рішення, мотивація, наслідки та статус реалізації. |
| [changes.md](changes.md) | Хронологічний дайджест значущих змін знань, реалізації й перевірок. |

## Як користуватися

На старті змістовної задачі спочатку синхронізуй branch із `origin/kb-only` за процедурою в `collaboration.md`; потім прочитай цей індекс і `status.md`, відкрий лише документи, потрібні за темою. Для фактичної поведінки MLT-5 звіряй знання з `../src/signal_proc/processing.py`, `../src/audio_contracts/packets.py`, `../README.md` та `../pyproject.toml`. Для майбутніх модулів позначай, що є вимогою або рекомендацією, а що реально реалізовано.

Після значущої зміни онови відповідний предметний документ, `status.md` і `changes.md` в тій самій роботі; fetch/rebase нові зміни інших агентів і запуш завершений результат у `origin/kb-only`. Дайджест має коротко пояснювати, що змінилося, чим це підтверджено та чи впливає це на поведінку/перевірку. Не дублюй великі розділи в кількох файлах. Невідоме називай невідомим; запланований тест або Jira-картка не є доказом фактичного результату. Усі KB-конфлікти вирішуй самостійно за `collaboration.md`, не передавай їх розробнику.

Дані з чотирьох наданих звітів і вбудованих у них Jira-знімків є історичними. Вони пояснюють вимоги, план тестування та задум, але не підтверджують актуальні Jira-статуси, реалізацію чи проходження тестів. Не зберігай особисті дані авторів/учасників.

## Розміщення і Git

- Проєктний remote: `https://github.com/VladislavCalculus/Muliprosessing-Analisis.git`.
- Єдина гілка для KB: orphan `kb-only`. Вона не має спільного предка з `main`; до неї не зливають код і не переносять її коміти в `main`.
- У кореневому репозиторії `knowledge-base/` є linked worktree на `kb-only`, а не незалежний вкладений clone. Спільний Git config дає йому той самий `origin`. Кореневий `.gitignore` не дозволяє випадково додати папку KB в `main`.
- У `kb-only` коміть лише Markdown-документи KB. Не додавай код, тести, залежності, генератори, локальні конфіги чи копії файлів із `main`.
- Кожен агент перед читанням робить fetch, інтегрує remote, а після зміни — fetch/rebase/push; Git merge policy та конфліктні правила описані в `collaboration.md`.

### Відновити KB після clone основного репозиторію

Виконай у корені проєкту, коли папки `knowledge-base/` ще немає:

```bash
git fetch origin refs/heads/kb-only:refs/remotes/origin/kb-only
git worktree add --track -b kb-only knowledge-base origin/kb-only
```

Якщо локальна гілка `kb-only` вже існує й не зайнята worktree, використай:

```bash
git worktree add knowledge-base kb-only
```

Якщо каталог уже існує, спочатку перевір його, гілку та `git worktree list`. Не клонуй поверх і не видаляй вміст.

### Перевірити, закомітити й опублікувати KB

```bash
git -C knowledge-base status --short --branch
git -C knowledge-base branch --show-current
git -C knowledge-base remote -v
git -C knowledge-base diff
```

Переконайся, що гілка — `kb-only`, робоче дерево містить лише очікувані KB-файли, а `origin` — вказаний вище GitHub. Після коміту публікуй саме цю гілку:

```bash
git -C knowledge-base add README.md collaboration.md jira.md architecture.md backlog.md data_contract.md testing.md decisions.md system.md status.md changes.md
git -C knowledge-base commit -m "Update project knowledge base"
git -C knowledge-base push origin HEAD:refs/heads/kb-only
git ls-remote origin refs/heads/kb-only
```

Не використовуй force push. Якщо remote випереджає локальний branch, спершу fetch і перевір історію/зміни. Перевірку походження гілок можна зробити через `git merge-base origin/main origin/kb-only`: для двох незалежних коренів спільного предка не буде.
