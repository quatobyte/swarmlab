"""Погода и поле ветра (BEES_SPEC §2.2, §6).

Ветер `w(x, y, z, t)` — горизонтальный вектор:

* базовый вектор силы `w_ref` (из состояния погоды), направление медленно
  поворачивается с постоянной угловой скоростью;
* порывы — сумма `gust_harmonics` бегущих синусоид по времени и координатам
  (периоды, длины волн, направления и фазы из `rng("weather")`) — дёшево, гладко,
  детерминированно;
* всё умножается на профиль приземного слоя `(z_agl / height_ref)^α`, ниже
  `min_agl` — как на `min_agl`.

Состояние погоды (`clear` / `windy` / `rain`) меняет марковская цепь на тике
решений (§6, DECISIONS №42): за тик `dt` переход случается с вероятностью
`dt / mean_duration_s` в одно из других разрешённых состояний поровну. При смене
состояния заново выбирается сила ветра `w_ref` из диапазона состояния. Цепь
берёт случайность из своего потока (`weather.chain`), чтобы не сдвигать порывы.

Переключатели (DECISIONS №38): `enabled: false` — всегда `clear`, без ветра и
дождя; `wind: false` — без ветра; `rain: false` — состояние `rain` не наступает.
"""

from __future__ import annotations

import numpy as np

from swarmlab.bees.params import WeatherParams, WindParams


class Weather:
    """Состояние погоды и ветер в точках пчёл."""

    def __init__(
        self,
        weather: WeatherParams,
        wind: WindParams,
        gen: np.random.Generator,
        chain: np.random.Generator | None = None,
    ) -> None:
        self.params = weather
        self.wind_params = wind
        self.enabled = weather.enabled
        self._chain = chain
        #: Разрешённые состояния цепи (в порядке спецификации).
        self.allowed = [
            k for k in ("clear", "windy", "rain") if weather.rain or not weather.states[k].rain
        ]
        # Порядок обращений к генератору фиксирован.
        initial = weather.initial if weather.initial in self.allowed else "clear"
        self.state = initial if weather.enabled else "clear"
        st = weather.states[self.state]
        self.w_ref = float(gen.uniform(*st.wind)) if weather.enabled else 0.0
        if not weather.wind:
            self.w_ref = 0.0
        self.rain = bool(st.rain) if weather.enabled else False
        self.direction0 = float(gen.uniform(0.0, 2 * np.pi))
        turn = np.deg2rad(wind.turn_rate_deg_s)
        self.turn_rate = turn if gen.random() < 0.5 else -turn

        k = wind.gust_harmonics
        self._gust_omega = 2 * np.pi / gen.uniform(*wind.gust_period_s, k)
        wave_dir = gen.uniform(0.0, 2 * np.pi, k)
        wavenumber = 2 * np.pi / gen.uniform(*wind.gust_wavelength, k)
        self._gust_k = wavenumber[:, None] * np.column_stack([np.cos(wave_dir), np.sin(wave_dir)])
        gust_dir = gen.uniform(0.0, 2 * np.pi, k)
        self._gust_u = np.column_stack([np.cos(gust_dir), np.sin(gust_dir)])  # (K,2)
        self._gust_phase = gen.uniform(0.0, 2 * np.pi, k)
        # Сумма K синусоид с амплитудой a/√K имеет СКО a/√2 — как одна синусоида с амплитудой a.
        self._gust_amp = wind.gust_amplitude / np.sqrt(k) if k else 0.0

    def update(self, dt: float) -> str | None:
        """Шаг марковской цепи за `dt` (тик решений); вернуть новое состояние, если сменилось."""
        if not self.enabled or self._chain is None or len(self.allowed) < 2:
            return None
        gen = self._chain
        # Два обращения к генератору на каждый тик — порядок не зависит от исхода.
        roll, pick = gen.random(), gen.random()
        if roll >= dt / self.params.mean_duration_s:
            return None
        others = [k for k in self.allowed if k != self.state]
        self.state = others[min(int(pick * len(others)), len(others) - 1)]
        st = self.params.states[self.state]
        self.w_ref = float(gen.uniform(*st.wind)) if self.params.wind else 0.0
        self.rain = bool(st.rain)
        return self.state

    @property
    def calm(self) -> bool:
        """Ветра нет совсем — расчёт поля можно пропустить."""
        return self.w_ref == 0.0

    def base_direction(self, t: float) -> np.ndarray:
        a = self.direction0 + self.turn_rate * t
        return np.array([np.cos(a), np.sin(a)])

    def wind_at(self, pos: np.ndarray, ground: np.ndarray, t: float) -> np.ndarray:
        """Вектор ветра `(N,3)` в точках `pos (N,3)`; `ground (N,)` — высота рельефа под ними."""
        out = np.zeros_like(pos)
        if self.calm or pos.shape[0] == 0:
            return out
        w = self.wind_params
        horizontal = np.broadcast_to(self.base_direction(t), (pos.shape[0], 2)).copy()
        if self._gust_k.shape[0]:
            phase = pos[:, :2] @ self._gust_k.T + (self._gust_omega * t + self._gust_phase)
            horizontal += self._gust_amp * (np.sin(phase) @ self._gust_u)
        agl = np.maximum(pos[:, 2] - ground, w.min_agl)
        profile = (agl / w.height_ref) ** w.shear_exponent
        out[:, :2] = horizontal * (self.w_ref * profile)[:, None]
        return out
