<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
                xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
                xmlns:gml="http://www.opengis.net/gml">
  <!--
    Two synthetic LoD2 buildings in NRW (Köln-area UTM32N coordinates).
    Building A: flat roof (code 1000), 15 m total height.
    Building B: gabled roof (code 3100), 12 m total height.
  -->
  <core:cityObjectMember>
    <bldg:Building gml:id="DENW_FLAT_01">
      <bldg:measuredHeight uom="urn:adv:uom:m">15.0</bldg:measuredHeight>
      <bldg:roofType>1000</bldg:roofType>
      <bldg:lod1Solid>
        <gml:Solid>
          <gml:exterior>
            <gml:CompositeSurface>
              <gml:surfaceMember>
                <gml:Polygon>
                  <gml:exterior>
                    <gml:LinearRing>
                      <gml:posList srsDimension="3">
                        359780 5645990 52.0
                        359800 5645990 52.0
                        359800 5646010 52.0
                        359780 5646010 52.0
                        359780 5645990 52.0
                      </gml:posList>
                    </gml:LinearRing>
                  </gml:exterior>
                </gml:Polygon>
              </gml:surfaceMember>
            </gml:CompositeSurface>
          </gml:exterior>
        </gml:Solid>
      </bldg:lod1Solid>
    </bldg:Building>
  </core:cityObjectMember>
  <core:cityObjectMember>
    <bldg:Building gml:id="DENW_GABLED_01">
      <bldg:measuredHeight uom="urn:adv:uom:m">12.0</bldg:measuredHeight>
      <bldg:roofType>3100</bldg:roofType>
      <bldg:lod1Solid>
        <gml:Solid>
          <gml:exterior>
            <gml:CompositeSurface>
              <gml:surfaceMember>
                <gml:Polygon>
                  <gml:exterior>
                    <gml:LinearRing>
                      <gml:posList srsDimension="3">
                        359900 5646100 50.0
                        359920 5646100 50.0
                        359920 5646120 50.0
                        359900 5646120 50.0
                        359900 5646100 50.0
                      </gml:posList>
                    </gml:LinearRing>
                  </gml:exterior>
                </gml:Polygon>
              </gml:surfaceMember>
            </gml:CompositeSurface>
          </gml:exterior>
        </gml:Solid>
      </bldg:lod1Solid>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
