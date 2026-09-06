export function CitySelect({ value, onChange }) {
  return (
    <label className="city-select">
      城市
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        maxLength={20}
        autoComplete="off"
      />
    </label>
  );
}
