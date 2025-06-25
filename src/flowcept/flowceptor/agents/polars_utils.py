import polars as pl

def summarize_result(code, result, original_cols: list[str], query: str) -> str:
    """
    Summarize the Polars result with local reduction for large DataFrames.
    - For wide DataFrames, selects top columns based on variance and uniqueness.
    - For long DataFrames, truncates to preview rows.
    - Constructs a detailed prompt for the LLM with original column context.
    """
    if isinstance(result, pl.DataFrame):
        df = result
        summary_reason = ""
        MAX_COLS = 10

        if df.width > MAX_COLS:
            # Separate numeric and non-numeric columns
            numeric_cols = [col for col in df.columns if pl.datatypes.is_numeric(df.schema[col])]
            non_numeric_cols = [col for col in df.columns if col not in numeric_cols]

            # Select top numeric columns by variance
            if numeric_cols:
                var_df = df.select([pl.col(c).var().alias(c) for c in numeric_cols])
                top_var_cols = sorted(
                    [(col, var_df[0, col]) for col in numeric_cols],
                    key=lambda x: x[1] if x[1] is not None else -np.inf,
                    reverse=True
                )
                top_var_cols = [col for col, _ in top_var_cols[:MAX_COLS // 2]]
            else:
                top_var_cols = []

            # Select top non-numeric (categorical) columns by uniqueness
            if non_numeric_cols:
                nunique_df = df.select([pl.col(c).n_unique().alias(c) for c in non_numeric_cols])
                top_cat_cols = sorted(
                    [(col, nunique_df[0, col]) for col in non_numeric_cols],
                    key=lambda x: x[1] if x[1] is not None else -np.inf,
                    reverse=True
                )
                top_cat_cols = [col for col, _ in top_cat_cols[:MAX_COLS - len(top_var_cols)]]
            else:
                top_cat_cols = []

            selected_cols = top_var_cols + top_cat_cols
            df = df.select(selected_cols)
            summary_reason = (
                f"(Top {len(top_var_cols)} numeric columns by variance and "
                f"{len(top_cat_cols)} categorical columns by uniqueness.)"
            )
        else:
            summary_reason = "(No column reduction applied.)"

        # Row preview
        if df.height > 5:
            preview_df = df.head(5)
            placeholder = pl.DataFrame({col: ["..."] for col in df.columns})
            preview_df = pl.concat([preview_df, placeholder], how="vertical")
        else:
            preview_df = df

        summary_text = preview_df.to_string()
        cols_str = ", ".join(original_cols)
        prompt = (
            f"The DataFrame result below is a result of the user query '{query}'. "
            f"It is a reduction of a larger DataFrame obtained by executing the following code:\n"
            f"{code}\n"
            f"on the original DataFrame `df` whose columns are: {cols_str}.\n"
            f"{summary_reason}\n"
            f"{summary_text}\n"
            "What did this code do in the first place in high-level words (do not give too much coding detail)? "
            "Please use the resulting DataFrame above to answer the user query."
        )
        return llm(prompt)

    # Handle Series, list, and numpy array results
    if isinstance(result, (list, np.ndarray)):
        items = list(result)
        text = "\n".join(str(x) for x in items)
        if len(text) > 2000:
            series = pl.Series("x", items)
            counts = series.value_counts().sort("counts", descending=True).head(10)
            summary_text = counts.to_string()
            prompt = (
                f"Here are the top items for query '{query}':\n"
                f"{summary_text}\n"
                "Summarize these findings."
            )
            return llm(prompt)
        else:
            prompt = (
                f"Summarize the following list result for query '{query}':\n"
                f"{text}"
            )
            return llm(prompt)

    # Fallback for other types
    prompt = (
        f"Summarize the following result for query '{query}':\n"
        f"{result}"
    )
    return llm(prompt)
