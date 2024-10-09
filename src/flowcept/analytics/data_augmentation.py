"""Data augmentation module."""

from typing import List
import h2o
import numpy as np
import pandas as pd
from h2o.automl import H2OAutoML
from typing_extensions import deprecated

h2o.init()


@deprecated
def train_model(
    df,
    x_cols: List[str],
    y_col: str,
    max_models=30,
    train_test_split_size=0.8,
    seed=1234,
):
    """Train model."""
    h2o_df = h2o.H2OFrame(df)
    train, test = h2o_df.split_frame(ratios=[train_test_split_size], seed=seed)
    aml = H2OAutoML(max_models=max_models, seed=seed)

    aml.train(x=x_cols, y=y_col, training_frame=train)
    return aml


@deprecated
def augment_df_linearly(df, N, cols_to_augment, seed=1234):
    """Linearly augment dataframe."""
    np.random.seed(seed)
    new_df = df.copy()
    new_df["original"] = 1

    augmented_data = {}

    # Linearly interpolate values and create new rows with 'original' = False
    for col in cols_to_augment:
        min_val = df[col].min()
        max_val = df[col].max()
        new_values = np.random.uniform(min_val, max_val, N)
        augmented_data[col] = new_values

    augmented_data["original"] = [0] * N

    appended_df = pd.concat([new_df, pd.DataFrame(augmented_data)], ignore_index=True)
    return appended_df


@deprecated
def augment_data(df, N, augmentation_model: H2OAutoML, x_cols, y_col):
    """Augment data."""
    new_df = augment_df_linearly(df, N, x_cols)
    h2odf = h2o.H2OFrame(new_df.loc[new_df["original"] == 0][x_cols])
    h2opred = augmentation_model.predict(h2odf)
    pred = np.array(h2opred.as_data_frame()["predict"])
    new_df.loc[new_df["original"] == 0, y_col] = pred
    return new_df
