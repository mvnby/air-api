/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductBrandResponse } from './ProductBrandResponse';
import type { ProductResponse } from './ProductResponse';
import type { ProductSeriesResponse } from './ProductSeriesResponse';
import type { PublicRelatedSeriesResponse } from './PublicRelatedSeriesResponse';
export type PublicSeriesPageResponse = {
    brand: ProductBrandResponse;
    series: ProductSeriesResponse;
    products?: Array<ProductResponse>;
    related_series?: Array<PublicRelatedSeriesResponse>;
};

