"""Table anchoring must survive bad model coordinates without changing readings."""
import io
from types import SimpleNamespace as NS

from PIL import Image, ImageDraw

from archivist.schema import BBox, Citation, ExtractedValue
from archivist.templates import ocr, table_v2


def fixture():
    image = Image.new('RGB', (400, 220), 'white')
    draw = ImageDraw.Draw(image)
    layer, values = [], []
    labels = ['Oct. 5', 'Oct. 12', 'Oct. 5', 'Oct. 12']
    for i, label in enumerate(labels):
        row = f'{i+1:02d}'
        y = 50+i*35
        layer.append(ocr.Word(label, BBox(x0=10,y0=y,x1=55,y1=y+10)))
        for column, x, number in [('a',200,123+i*111),('b',300,567+i*111)]:
            b=BBox(x0=x,y0=y,x1=x+20,y1=y+10)
            layer.append(ocr.Word(str(number), b))
            draw.rectangle((x,y,x+19,y+9), fill='black')
            # Boxes point elsewhere; unique OCR and table labels must decide.
            values.append(ExtractedValue(field_id=f'T.table:p:{row}:{column}', value=str(number),
                citation=Citation(page_id='p',bbox=BBox(x0=230,y0=10,x1=250,y1=20)),abstained=False))
        values.append(ExtractedValue(field_id=f'T.table:p:{row}:label',value=label,
            citation=Citation(page_id='p',bbox=BBox(x0=10,y0=10,x1=55,y1=20)),abstained=False))
    out=io.BytesIO(); image.save(out,format='PNG')
    layout=NS(columns=[NS(key='label',kind='text'),NS(key='a',kind='money'),NS(key='b',kind='money')],
              rows=NS(read=4),row_keys=['01','02','03','04'])
    return values,layer,NS(layout=layout),out.getvalue()


def run(values,layer,t,image):
    old=(values,{v.field_id:'model' for v in values},{'order':None})
    return table_v2.assign(values,t,image,layer,fallback=old)


def test_repeated_labels_use_occurrences_despite_boxes_on_wrong_row():
    values,layer,t,image=fixture()
    result,sources,info=run(values,layer,t,image)
    assert info['repeated_labels']['oct5']=={'read':2,'ocr':2}
    assert [v.value for v in result]==[v.value for v in values]
    assert [v.field_id for v in result]==[v.field_id for v in values]
    for v in result:
        if v.field_id.endswith(':label'): continue
        row=int(v.field_id.split(':')[-2])-1
        assert v.citation.bbox.y0 <= 50+row*35
        assert v.citation.bbox.y1 >= 60+row*35
        assert sources[v.field_id]=='table:ocr'
        assert v.citation.raw_bbox is None


def test_wrong_first_value_is_boxed_at_its_named_cell_not_at_matching_digits():
    values,layer,t,image=fixture()
    values[0]=values[0].model_copy(update={'value':'99999'})
    result,sources,info=run(values,layer,t,image)
    assert result[0].value=='99999'
    assert result[0].citation.bbox.x0 < 200
    assert result[0].citation.bbox.y0 < 50
    assert result[0].citation.bbox.y1 > 60
    assert sources[result[0].field_id]=='table:ocr'


def test_extra_repeated_label_does_not_shift_later_occurrences():
    values,layer,t,image=fixture()
    layer.append(ocr.Word('Oct. 5',BBox(x0=10,y0=190,x1=55,y1=200)))
    result,sources,info=run(values,layer,t,image)
    assert info['repeated_labels']['oct5']=={'read':2,'ocr':3}
    assert all(v['source']!='label-occurrence' for r,v in info['rows'].items() if r in ('01','03'))
    assert result[0].value==values[0].value


def test_no_text_layer_keeps_v1_and_records_fallback():
    values,layer,t,image=fixture()
    result,sources,info=run(values,[],t,image)
    assert result==values
    assert set(sources.values())=={'v1:model'}
    assert info['columns']=={}
