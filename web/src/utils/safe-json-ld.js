export function safeJsonLd(value) {
    const serialized = JSON.stringify(value);
    if (serialized === undefined) return "";

    return serialized
        .replace(/</g, "\\u003c")
        .replace(/>/g, "\\u003e")
        .replace(/&/g, "\\u0026")
        .replace(/\u2028/g, "\\u2028")
        .replace(/\u2029/g, "\\u2029");
}
